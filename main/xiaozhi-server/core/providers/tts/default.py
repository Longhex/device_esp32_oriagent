import os
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSNotConfiguredError(RuntimeError):
    """TTS provider real chưa khởi tạo được — dùng để fail-fast thay vì spam log."""
    pass


class DefaultTTS(TTSProviderBase):
    def __init__(self, config, delete_audio_file=True):
        super().__init__(config, delete_audio_file)
        self.output_dir = config.get("output_dir", "tmp")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        logger.bind(tag=TAG).warning(
            "DefaultTTS fallback đang được dùng — TTS provider thực tế chưa init thành công. "
            "Mọi text_to_speak() sẽ raise. Kiểm tra config TTS trong Manager UI hoặc config.yaml."
        )

    def generate_filename(self):
        """生成唯一的音频文件名"""
        import uuid

        return os.path.join(self.output_dir, f"{uuid.uuid4()}.wav")

    async def text_to_speak(self, text, output_file):
        # Fail-fast: tránh spam log mỗi lần TTS gen
        raise TTSNotConfiguredError(
            "TTS provider chưa được cấu hình hoặc khởi tạo thất bại. "
            "Kiểm tra config TTS (api_key, endpoint, network)."
        )
