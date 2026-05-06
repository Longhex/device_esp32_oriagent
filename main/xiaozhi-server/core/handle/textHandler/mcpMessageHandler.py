import asyncio
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.providers.tools.device_mcp import handle_mcp_message


class McpTextMessageHandler(TextMessageHandler):
    """MCP消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.MCP

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        if "payload" in msg_json:
            if not hasattr(conn, "mcp_client") or not conn.mcp_client:
                conn.logger.bind(tag=TAG).warning("Device sent MCP message but mcp_client is not initialized. Initializing now.")
                from core.providers.tools.device_mcp import MCPClient
                conn.mcp_client = MCPClient()

            asyncio.create_task(
                handle_mcp_message(conn, conn.mcp_client, msg_json["payload"])
            )