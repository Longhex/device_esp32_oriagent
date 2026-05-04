import asyncio
import json
from unittest.mock import MagicMock
import sys
import os

# Thêm đường dẫn vào sys.path để có thể import các module của dự án
sys.path.append(os.path.join(os.getcwd(), "main", "xiaozhi-server"))

from core.utils import textUtils

class MockConnection:
    def __init__(self):
        self.websocket = MagicMock()
        self.websocket.send = self.mock_send
        self.session_id = "test_session_123"
        self.sent_messages = []
        self.logger = MagicMock()

    async def mock_send(self, message):
        self.sent_messages.append(json.loads(message))
        # In ra payload để quan sát
        print(f"\n[SERVER -> DEVICE] Payload: {message}")

async def test_emoji_flow():
    conn = MockConnection()
    
    print("=== BẮT ĐẦU TEST LUỒNG EMOJI ===")

    # Danh sách các câu trả lời giả định từ LLM
    test_cases = [
        "😂 Haha, buồn cười quá đi mất!",
        "😭 Huhu, mình đang cảm thấy rất buồn...",
        "😠 Bạn làm mình giận rồi đấy!",
        "🤔 Để mình suy nghĩ một chút nhé.",
        "Chào bạn, hôm nay bạn thế nào? (Không có emoji)"
    ]

    for raw_text in test_cases:
        print(f"\n--- Test Case: '{raw_text}' ---")
        
        # GIAI ĐOẠN 1: Nhận diện cảm xúc và gửi lệnh đổi mặt (type: llm)
        print("Giai đoạn 1: Trích xuất cảm xúc...")
        await textUtils.get_emotion(conn, raw_text)
        
        # GIAI ĐOẠN 2: Làm sạch văn bản để gửi đi nói (TTS) hoặc hiển thị (STT)
        print("Giai đoạn 2: Làm sạch văn bản (Xóa emoji)...")
        cleaned_text = textUtils.check_emoji(raw_text)
        print(f"Văn bản sau khi làm sạch: '{cleaned_text}'")
        
        # Mô phỏng bản tin STT/TTS gửi xuống thiết bị
        stt_payload = {
            "type": "stt",
            "text": cleaned_text,
            "session_id": conn.session_id
        }
        await conn.mock_send(json.dumps(stt_payload, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_emoji_flow())
