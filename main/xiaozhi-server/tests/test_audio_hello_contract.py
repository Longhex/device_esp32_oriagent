import asyncio
import copy
import json
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.handle.helloHandle import handleHelloMessage  # noqa: E402


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, message):
        self.messages.append(json.loads(message))

    async def close(self, **_kwargs):
        self.closed = True


class FakeLogger:
    def bind(self, **_kwargs):
        return self

    def debug(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


class AudioHelloContractTest(unittest.TestCase):
    def test_client_uplink_does_not_overwrite_server_downlink(self):
        welcome = {
            "type": "hello",
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        conn = SimpleNamespace(
            logger=FakeLogger(),
            websocket=FakeWebSocket(),
            welcome_msg=copy.deepcopy(welcome),
            output_sample_rate=24000,
            features=None,
        )
        asyncio.run(
            handleHelloMessage(
                conn,
                {
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": 16000,
                        "channels": 1,
                        "frame_duration": 60,
                    }
                },
            )
        )
        self.assertEqual(conn.input_sample_rate, 16000)
        self.assertEqual(conn.welcome_msg["audio_params"]["sample_rate"], 24000)
        self.assertEqual(conn.websocket.messages[-1]["audio_params"]["sample_rate"], 24000)
        self.assertEqual(welcome["audio_params"]["sample_rate"], 24000)


if __name__ == "__main__":
    unittest.main()
