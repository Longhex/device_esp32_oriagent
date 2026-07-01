"""
Pytest conftest cho xiaozhi-server tests.

Máy dev/CI có thể CHƯA cài thư viện C `opus` → `import opuslib_next` chết, kéo theo
cả chuỗi import của core.providers.tts.base. Vì các provider opus-direct (V3/V4)
KHÔNG dùng tới opus encoder ở tầng logic cần test, ta stub opuslib_next để import
chuỗi base chạy được. Stub này chỉ ảnh hưởng test, không đụng runtime thật.
"""
import os
import sys
import types

# Cho phép `import core.*` khi chạy pytest từ bất kỳ đâu.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # .../xiaozhi-server
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if "opuslib_next" not in sys.modules:
    try:
        import opuslib_next  # noqa: F401  (đã cài lib C thật → dùng luôn)
    except Exception:
        op = types.ModuleType("opuslib_next")

        class OpusError(Exception):
            pass

        op.OpusError = OpusError
        op.Encoder = object
        op.Decoder = object
        consts = types.ModuleType("opuslib_next.constants")
        consts.APPLICATION_AUDIO = 2049
        consts.APPLICATION_VOIP = 2048
        op.constants = consts
        sys.modules["opuslib_next"] = op
        sys.modules["opuslib_next.constants"] = consts
