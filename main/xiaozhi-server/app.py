import os
import signal
import sys
import uuid
import asyncio
from aioconsole import ainput

from config.settings import load_config
from config.logger import setup_logging
from core.utils.util import get_local_ip, validate_mcp_endpoint
from core.http_server import SimpleHttpServer
from core.websocket_server import WebSocketServer
from core.utils.util import check_ffmpeg_installed
from core.utils.gc_manager import get_gc_manager

TAG = __name__
logger = setup_logging()

VALID_TRANSPORT_MODES = {
    "websocket_legacy",
    "mqtt_udp_hybrid",
    "livekit_bridge",
}


def _is_truthy_env(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def resolve_transport_mode() -> str:
    transport_mode_env = os.environ.get("TRANSPORT_MODE")
    if transport_mode_env is not None:
        transport_mode = transport_mode_env.strip().lower()
        if transport_mode not in VALID_TRANSPORT_MODES:
            logger.bind(tag=TAG).warning(
                f"Unsupported TRANSPORT_MODE={transport_mode_env}, fallback to websocket_legacy"
            )
            return "websocket_legacy"
        if transport_mode == "livekit_bridge":
            logger.bind(tag=TAG).warning(
                "TRANSPORT_MODE=livekit_bridge is not implemented in Phase 1, fallback to websocket_legacy"
            )
            return "websocket_legacy"
        return transport_mode

    logger.bind(tag=TAG).info(
        "TRANSPORT_MODE not set, using ENABLE_HYBRID_GATEWAY compatibility flag"
    )
    if _is_truthy_env(os.environ.get("ENABLE_HYBRID_GATEWAY", "false")):
        return "mqtt_udp_hybrid"
    return "websocket_legacy"


def resolve_server_auth_key(config: dict) -> str:
    """Resolve auth_key without forcing test defaults into production paths."""
    auth_key = config["server"].get("auth_key", "")

    if not auth_key or len(auth_key) == 0 or "你" in auth_key:
        auth_key = config.get("manager-api", {}).get("secret", "")
        if not auth_key or len(auth_key) == 0 or "你" in auth_key:
            auth_key = str(uuid.uuid4().hex)

    test_auth = os.environ.get("HYBRID_TEST_AUTH_KEY", "").strip()
    if test_auth:
        logger.bind(tag=TAG).warning(
            "HYBRID_TEST_AUTH_KEY override enabled for this process"
        )
        auth_key = test_auth

    return auth_key


async def wait_for_exit() -> None:
    """
    阻塞直到收到 Ctrl‑C / SIGTERM。
    - Unix: 使用 add_signal_handler
    - Windows: 依赖 KeyboardInterrupt
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if sys.platform != "win32":  # Unix / macOS
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    else:
        # Windows：await一个永远pending的fut，
        # 让 KeyboardInterrupt 冒泡到 asyncio.run，以此消除遗留普通线程导致进程退出阻塞的问题
        try:
            await asyncio.Future()
        except KeyboardInterrupt:  # Ctrl‑C
            pass


async def monitor_stdin():
    """监控标准输入，消费回车键"""
    while True:
        await ainput()  # 异步等待输入，消费回车


async def main():
    check_ffmpeg_installed()
    config = load_config()
    transport_mode = resolve_transport_mode()
    logger.bind(tag=TAG).info(f"Transport mode resolved: {transport_mode}")

    config["server"]["auth_key"] = resolve_server_auth_key(config)

    # BẮT MẠCH: In cấu hình Auth thực tế mà Server đang dùng
    auth_info = config.get("server", {}).get("auth", {})
    logger.bind(tag=TAG).info(f"=== AUTH CONFIG LOADED: enabled={auth_info.get('enabled')}, allowed_devices={auth_info.get('allowed_devices')} ===")

    # 添加 stdin 监控任务
    stdin_task = asyncio.create_task(monitor_stdin())

    # 启动全局GC管理器（5分钟清理一次）
    gc_manager = get_gc_manager(interval_seconds=300)
    await gc_manager.start()

    # 启动 WebSocket 服务器
    ws_server = WebSocketServer(config)
    ws_task = asyncio.create_task(ws_server.start())

    udp_manager = None
    udp_task = None
    mqtt_server = None
    mqtt_task = None
    if transport_mode == "mqtt_udp_hybrid":
        logger.bind(tag=TAG).info("Hybrid gateway enabled: starting MQTT signaling + UDP media services")
        from core.udp_server import udp_manager
        udp_task = asyncio.create_task(udp_manager.start_server(port=5000))

        from core.mqtt_server import MqttServer
        mqtt_server = MqttServer(config, ws_server)
        mqtt_task = asyncio.create_task(mqtt_server.start())
    else:
        logger.bind(tag=TAG).info("Hybrid gateway disabled: WebSocket voice path remains active as the default transport")

    # 启动 Simple http 服务器
    ota_server = SimpleHttpServer(config)
    ota_task = asyncio.create_task(ota_server.start())

    read_config_from_api = config.get("read_config_from_api", False)
    port = int(config["server"].get("http_port", 8003))
    logger.bind(tag=TAG).info(
        "OTA Interface:\t\thttp://{}:{}/xiaozhi/ota/",
        get_local_ip(),
        port,
    )
    logger.bind(tag=TAG).info(
        "Vision API:\thttp://{}:{}/mcp/vision/explain",
        get_local_ip(),
        port,
    )
    mcp_endpoint = config.get("mcp_endpoint", None)
    if mcp_endpoint is not None and "你" not in mcp_endpoint:
        # 校验MCP接入点格式
        if validate_mcp_endpoint(mcp_endpoint):
            logger.bind(tag=TAG).info("MCP Endpoint:\t{}", mcp_endpoint)
            # 将mcp计入点地址转成调用点
            mcp_endpoint = mcp_endpoint.replace("/mcp/", "/call/")
            config["mcp_endpoint"] = mcp_endpoint
        else:
            logger.bind(tag=TAG).error("MCP endpoint format is invalid")
            config["mcp_endpoint"] = "Your websocket address"

    # 获取WebSocket配置，使用安全的默认值
    websocket_port = 8000
    server_config = config.get("server", {})
    if isinstance(server_config, dict):
        websocket_port = int(server_config.get("port", 8000))

    logger.bind(tag=TAG).info(
        "Websocket Address:\tws://{}:{}/xiaozhi/v1/",
        get_local_ip(),
        websocket_port,
    )

    logger.bind(tag=TAG).info(
        "======= Above is the websocket address, do not visit with a browser ======="
    )
    logger.bind(tag=TAG).info(
        "To test websocket, please open test/test_page.html in Chrome"
    )
    logger.bind(tag=TAG).info(
        "=============================================================\n"
    )

    try:
        await wait_for_exit()  # 阻塞直到收到退出信号
    except asyncio.CancelledError:
        print("Task cancelled, cleaning up resources...")
    finally:
        # 停止全局GC管理器
        await gc_manager.stop()

        if mqtt_server:
            try:
                await mqtt_server.stop()
            except Exception as mqtt_stop_error:
                logger.bind(tag=TAG).warning(f"MQTT stop warning: {mqtt_stop_error}")

        if udp_manager:
            try:
                await udp_manager.stop_server()
            except Exception as udp_stop_error:
                logger.bind(tag=TAG).warning(f"UDP stop warning: {udp_stop_error}")

        # 取消所有任务（关键修复点）
        stdin_task.cancel()
        ws_task.cancel()
        if mqtt_task:
            mqtt_task.cancel()
        if udp_task:
            udp_task.cancel()
        if ota_task:
            ota_task.cancel()

        # 等待任务终止（必须加超时）
        wait_tasks = [stdin_task, ws_task]
        if ota_task:
            wait_tasks.append(ota_task)
        if udp_task:
            wait_tasks.append(udp_task)
        if mqtt_task:
            wait_tasks.append(mqtt_task)
        await asyncio.wait(
            wait_tasks,
            timeout=3.0,
            return_when=asyncio.ALL_COMPLETED,
        )
        print("Server closed, program exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Manual interrupt, program terminated.")
