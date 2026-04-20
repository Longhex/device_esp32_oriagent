import os
import asyncio
import httpx
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

class TTSProvider(TTSProviderBase):
    """
    Vbee TTS Provider (Standard V1 - Indirect Flow with Optimized Polling)
    Reference: https://vbee.vn/api/public/v1/voices for voice codes
    """
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_token = config.get("api_token")
        self.app_id = config.get("app_id")
        self.callback_url = config.get("callback_url")
        if not self.callback_url:
            self.callback_url = "http://device.oriagent.com/callback"
            logger.bind(tag=TAG).info(f"Vbee: callback_url is empty, using fallback: {self.callback_url}")
        
        # Security audit log
        masked_token = self._mask_token(self.api_token)
        logger.bind(tag=TAG).debug(f"VbeeProvider Init | AppID: {self.app_id} | Token: {masked_token} | Callback: {self.callback_url}")
        
        # Mandatory field validation
        if not self.api_token or not self.app_id:
            missing = []
            if not self.api_token: missing.append("api_token")
            if not self.app_id: missing.append("app_id")
            logger.bind(tag=TAG).error(f"Vbee TTS config missing mandatory fields: {', '.join(missing)}")

        # Voice and Audio parameters
        # Recommended voice: hn_female_ngochuyen_full_48k-fhg
        self.voice = config.get("voice", "hn_female_ngochuyen_full_48k-fhg")
        self.bitrate = config.get("bitrate", 128)
        self.audio_type = config.get("audio_type", "wav") # Using wav for direct playback compatibility
        
        # Speed rate validation (Vbee Range: 0.1 - 1.9)
        speed_rate = config.get("rate", 1.0)
        try:
            self.speed_rate = float(speed_rate)
            self.speed_rate = max(0.1, min(1.9, self.speed_rate))
        except (ValueError, TypeError):
            self.speed_rate = 1.0

        self.api_base_url = "https://vbee.vn/api/v1/tts"

    def _mask_token(self, token):
        if not token or len(str(token)) < 10:
            return "***"
        s_token = str(token)
        return f"{s_token[:6]}...{s_token[-4:]}"

    async def text_to_speak(self, text, output_file):
        """Main entry point for TTS synthesis using async I/O"""
        if not self.api_token or not self.app_id:
            raise Exception("Vbee TTS is not properly configured. Missing api_token or app_id.")

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Payload based on Vbee V1 schema
        payload = {
            "app_id": self.app_id,
            "response_type": "indirect",
            "callback_url": self.callback_url,
            "input_text": text,
            "voice_code": self.voice,
            "audio_type": self.audio_type,
            "bitrate": self.bitrate,
            "speed_rate": self.speed_rate,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                # Step 1: Create TTS Request
                response = await client.post(self.api_base_url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    logger.bind(tag=TAG).error(f"Vbee POST failed | Status: {response.status_code} | Body: {response.text[:300]}")
                    raise Exception(f"Vbee creation failed (HTTP {response.status_code})")

                res_json = response.json()
                if res_json.get("status") != 1:
                    error_msg = res_json.get("error_message") or res_json.get("message") or "Unknown API error"
                    logger.bind(tag=TAG).error(f"Vbee API reported error: {error_msg}")
                    raise Exception(f"Vbee API Error: {error_msg}")

                request_id = res_json.get("result", {}).get("request_id")
                if not request_id:
                    raise Exception("Vbee response missing request_id")

                # Step 2: High-frequency Polling for completion
                audio_link = await self._poll_audio_link(client, request_id, headers)
                
                # Step 3: Download synthesized audio
                audio_response = await client.get(audio_link)
                if audio_response.status_code != 200:
                    raise Exception(f"Failed to download audio from {audio_link} (HTTP {audio_response.status_code})")

                # Step 4: Save to file or return bytes
                if output_file:
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    with open(output_file, "wb") as f:
                        f.write(audio_response.content)
                    return output_file
                
                return audio_response.content

            except Exception as e:
                logger.bind(tag=TAG).error(f"Vbee synthesis failure: {str(e)}")
                raise

    async def _poll_audio_link(self, client: httpx.AsyncClient, request_id, headers):
        """Poll the Vbee status endpoint with high frequency to minimize TTFA"""
        poll_url = f"{self.api_base_url}/{request_id}"
        max_attempts = 50 
        interval = 0.2  # High frequency polling (200ms)

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(poll_url, headers=headers)
                if response.status_code != 200:
                    await asyncio.sleep(interval)
                    continue

                res_json = response.json()
                result = res_json.get("result", {})
                status = result.get("status")

                if status == "SUCCESS":
                    audio_link = result.get("audio_link")
                    if audio_link:
                        return audio_link
                    raise Exception("Vbee reported SUCCESS but audio_link is missing")
                
                elif status == "FAILURE":
                    error_msg = result.get("error_message") or "Vbee task processing error"
                    raise Exception(f"Vbee task failed: {error_msg}")

                # Wait for next poll cycle
                await asyncio.sleep(interval)

            except Exception as e:
                if "Vbee task failed" in str(e):
                    raise e
                if attempt == max_attempts:
                    raise Exception(f"Vbee polling timeout after {max_attempts} attempts")
                await asyncio.sleep(interval)

        raise Exception(f"Vbee polling timeout [request_id: {request_id}]")
