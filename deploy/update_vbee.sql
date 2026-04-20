USE xiaozhi_esp32_server;
UPDATE ai_model_config 
SET config_json = '{"type": "vbee", "api_token": "", "app_id": "", "callback_url": "", "voice": "hn_female_ngochuyen_full_48k-fhg", "rate": "1.0"}' 
WHERE id = 'TTS_Vbee';
