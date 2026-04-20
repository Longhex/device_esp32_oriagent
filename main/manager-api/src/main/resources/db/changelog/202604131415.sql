-- Register Oriagent LLM Provider
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('SYSTEM_LLM_oriagent_ws', 'LLM', 'oriagent_ws', 'Oriagent', 
'[{"key":"api_url","label":"URL API (Dify/Oriagent)","type":"string"},{"key":"api_key","label":"API Key (Bearer Token)","type":"string"},{"key":"model_name","label":"Tên Model (Mặc định: oriagent-default)","type":"string"}]', 
20, 1, NOW(), 1, NOW());

-- Add Default Oriagent LLM Configuration
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('LLM_OriagentLLM', 'LLM', 'OriagentLLM', 'Oriagent', 0, 1, 
'{"type": "oriagent_ws", "api_url": "http://localhost:8080/v1/chat-messages", "api_key": "your_api_key", "model_name": "oriagent-default"}', 
NULL, 'Oriagent LLM Provider', 20, 1, NOW(), 1, NOW());

-- Register ElevenLabs TTS Provider
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('SYSTEM_TTS_elevenlabs', 'TTS', 'elevenlabs', 'ElevenLabs', 
'[{"key":"api_key","label":"xi-api-key","type":"string"},{"key":"voice_id","label":"Voice ID","type":"string"},{"key":"model_id","label":"Model ID (Mặc định: eleven_multilingual_v2)","type":"string"}]', 
30, 1, NOW(), 1, NOW());

-- Register Vbee TTS Provider
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('SYSTEM_TTS_vbee', 'TTS', 'vbee', 'Vbee (Việt Nam)', 
'[{"key":"api_token","label":"API Token (Bearer)","type":"string"},{"key":"app_id","label":"App ID","type":"string"},{"key":"voice","label":"Voice Code (Ví dụ: hn_female_xuananh_news_48k-h)","type":"string"},{"key":"rate","label":"Tốc độ (Mặc định: 1)","type":"string"}]', 
31, 1, NOW(), 1, NOW());

-- Add Default ElevenLabs Configuration
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('TTS_ElevenLabs', 'TTS', 'elevenlabs', 'ElevenLabs TTS', 0, 1, 
'{"type": "elevenlabs", "api_key": "YOUR_KEY", "voice_id": "21m00Tcm4lPqWRM9sxW1", "model_id": "eleven_multilingual_v2"}', 
'ElevenLabs TTS Provider', 30, 1, NOW(), 1, NOW());

-- Add Default Vbee Configuration
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`) 
VALUES ('TTS_Vbee', 'TTS', 'vbee', 'Vbee Vietnamese TTS', 0, 1, 
'{"type": "vbee", \"app_id\": \"YOUR_APP_ID\", \"api_token\": \"YOUR_TOKEN\", \"voice\": \"hn_female_xuananh_news_48k-h\", \"rate\": 1}', 
'Vbee Vietnamese TTS Provider', 31, 1, NOW(), 1, NOW());
