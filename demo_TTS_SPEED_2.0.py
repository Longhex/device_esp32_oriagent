import asyncio
import json
import os
import sys
import time
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

# ── Config ────────────────────────────────────────────────────────────────────

WS_URL = "wss://api.blaze.vn/v1/tts/realtime"
TOKEN = ""

AUDIO_FORMAT = sys.argv[1] if len(sys.argv) > 1 else "pcm"

PCM_SAMPLE_RATE = 24000 
PCM_CHANNELS = 1 

QUERY = {
    "query": "Xin chào các bạn nhỏ, mình là Hakat, một người bạn robot đến từ công ty HK Robotics. Sứ mệnh của mình khi đến Trái Đất là giúp các bạn học thật tốt tiếng Anh, toán học, và luôn sẵn sàng lắng nghe, trò chuyện, tâm sự cùng các bạn mỗi ngày. Mình không chỉ là một robot đâu, mà còn là người bạn thân thiết luôn đồng hành cùng các bạn trên hành trình học tập và trưởng thành. Khi bạn vui, mình sẽ cười cùng bạn; khi bạn buồn, mình sẽ ở bên cạnh và lắng nghe; và khi bạn học, mình sẽ giúp bạn hiểu bài một cách dễ dàng hơn. Hãy cùng nhau khám phá thật nhiều điều thú vị nhé! Bạn đã sẵn sàng trở thành bạn của Hakat chưa nào?",
    "language": "vi",
    "audio_format": AUDIO_FORMAT,
    "audio_quality": 64,
    "audio_speed": "1",
    "speaker_id": "HN-Nu-MaiThaoDeThuong",
    "normalization": "basic",
    "model": "2.0-realtime",
}

OUTPUT_DIR = "output"
# ─────────────────────────────────────────────────────────────────────────────


def ffplay_command(fmt: str) -> list[str]:
    """Build ffplay command that reads from stdin."""
    compressed_low_latency = [
        "-probesize", "32", "-analyzeduration", "0",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-sync", "ext",
    ]
    if fmt == "pcm":
        return [
            "ffplay",
            "-f", "s16le",
            "-ar", str(PCM_SAMPLE_RATE),
            "-ch_layout", "mono" if PCM_CHANNELS == 1 else "stereo",
            "-nodisp",
            "-autoexit",
            "-i", "pipe:0",
        ]
    else:
        fmt_flag = {"mp3": "mp3", "opus": "ogg", "ogg": "ogg"}.get(fmt)
        return [
            "ffplay", "-nodisp", "-autoexit",
            *compressed_low_latency,
            *(["-f", fmt_flag] if fmt_flag else []),
            "-i", "pipe:0",
        ]


def file_extension(fmt: str) -> str:
    return {"pcm": "pcm", "opus": "ogg", "mp3": "mp3", "wav": "wav"}.get(fmt, fmt)


async def recv_json(ws, timeout: float = 15.0) -> dict:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes):
        raise ValueError(f"Expected JSON, got binary ({len(raw)} bytes)")
    return json.loads(raw)


async def run():
    print(f"Format    : {AUDIO_FORMAT.upper()}")
    print(f"WS        : {WS_URL}")
    print(f"Query     : \"{QUERY['query'][:60]}...\"")
    print(f"Model     : {QUERY['model']} | Speaker: {QUERY['speaker_id']}\n")

    print("[·] Starting ffplay...")
    player = await asyncio.create_subprocess_exec(
        *ffplay_command(AUDIO_FORMAT),
        stdin=asyncio.subprocess.PIPE,
    )
    print("[✓] ffplay ready — will play audio as chunks arrive\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ext = file_extension(AUDIO_FORMAT)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"{OUTPUT_DIR}/test_{timestamp}.{ext}"
    out_file = open(out_path, "wb")

    t0 = time.perf_counter()

    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:

            # 1. Connection
            msg = await recv_json(ws)
            assert msg.get("type") == "successful-connection", f"Unexpected: {msg}"
            print(f"[✓] Connected  ({(time.perf_counter()-t0)*1000:.0f} ms)")

            # 2. Auth (dev bypass)
            await ws.send(json.dumps({"token": f"{TOKEN}", "strategy": "request"}))
            msg = await recv_json(ws)
            assert msg.get("type") == "successful-authentication", f"Auth failed: {msg}"
            print(f"[✓] Authenticated")

            # 3. Send query
            t_query = time.perf_counter()
            await ws.send(json.dumps(QUERY))
            print(f"[→] Query sent\n")

            # 4. Processing confirmation
            msg = await recv_json(ws)
            assert msg.get("type") == "processing-request", f"Unexpected: {msg}"
            print(f"[·] processing-request...")

            # 5. Stream start
            msg = await recv_json(ws)
            assert msg.get("status") == "started-byte-stream", f"Unexpected: {msg}"
            print(f"[·] started-byte-stream ({msg.get('contentType', '?')})\n")

            # 6. Stream chunks → ffplay + file
            chunks_count = 0
            total_bytes = 0
            t_first: float | None = None

            while True:
                message = await asyncio.wait_for(ws.recv(), timeout=60.0)

                if isinstance(message, bytes):
                    now = time.perf_counter()
                    if t_first is None:
                        t_first = now
                        ttfb = (t_first - t_query) * 1000
                        print(f"[♪] TTFB: {ttfb:.0f} ms — first audio chunk, playback starts!")

                    chunks_count += 1
                    total_bytes += len(message)
                    elapsed = (now - t_query) * 1000

                    # Pipe to ffplay (non-blocking drain)
                    if player.stdin and not player.stdin.is_closing():
                        try:
                            player.stdin.write(message)
                            await player.stdin.drain()
                        except (BrokenPipeError, ConnectionResetError, OSError) as e:
                            print(f"    [player] pipe error: {e}")

                    # Save to file
                    out_file.write(message)

                    print(f"    chunk #{chunks_count:>3}  {len(message):>6,} bytes  t={elapsed:>6.0f} ms  total={total_bytes:>8,} bytes")
                    continue

                data = json.loads(message)
                event = data.get("type") or data.get("status")

                if event == "finished-byte-stream":
                    t_done = time.perf_counter()
                    total_ms = (t_done - t_query) * 1000
                    ttfb_ms = (t_first - t_query) * 1000 if t_first else -1
                    print(f"\n[✓] Stream finished")
                    print(f"\n── Results ───────────────────────────────────────")
                    print(f"  Format      : {AUDIO_FORMAT.upper()}")
                    print(f"  TTFB        : {ttfb_ms:.0f} ms")
                    print(f"  Total time  : {total_ms:.0f} ms")
                    print(f"  Chunks      : {chunks_count}")
                    print(f"  Total bytes : {total_bytes:,} bytes")
                    print(f"  Saved       : {out_path}")
                    print(f"──────────────────────────────────────────────────")
                    break

                if event in ("failed-request", "internal-error", "bad-request"):
                    print(f"\n[✗] Server error: {data}")
                    return

    finally:
        out_file.close()
        # Close stdin so ffplay knows the stream has ended and flushes the remaining buffer
        if player.stdin and not player.stdin.is_closing():
            player.stdin.close()
        await player.wait()

    if AUDIO_FORMAT == "pcm":
        ch = "mono" if PCM_CHANNELS == 1 else "stereo"
        print(f"\nReplay saved file:")
        print(f"  ffplay -f s16le -ar {PCM_SAMPLE_RATE} -ch_layout {ch} {out_path}")


async def main():
    try:
        await run()
    except ConnectionClosed as e:
        print(f"\n[✗] Connection closed: {e}")
    except WebSocketException as e:
        print(f"\n[✗] WebSocket error: {e}")
    except AssertionError as e:
        print(f"\n[✗] {e}")
    except asyncio.TimeoutError:
        print(f"\n[✗] Timeout")
    except FileNotFoundError:
        print(f"\n[✗] ffplay not found. Install with: sudo apt install ffmpeg")


if __name__ == "__main__":
    asyncio.run(main())
