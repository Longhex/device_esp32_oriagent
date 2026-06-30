-- Re-register Oriagent Voice TTS as a WebSocket realtime provider (VoxCPM Voice Clone TTS API v1).
-- Khác bản REST cũ: mỗi API key = một giọng; config lưu danh sách voices [{name,language,api_key}].
-- Form "Thông tin gọi" ở manager-web render UI đa giọng riêng dựa trên provider_code = oriagent_voice.

-- ===== TTS provider (WebSocket realtime) =====
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_oriagent_voice';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_TTS_oriagent_voice', 'TTS', 'oriagent_voice', 'Voice Oriagent (TTS realtime)',
'[{"key":"api_url","label":"URL API (mặc định: https://voice.oriagent.com/api/v1)","type":"string"},{"key":"voices","label":"Danh sách giọng (mỗi API key một giọng)","type":"array"}]',
48, 1, NOW(), 1, NOW());

-- ===== TTS default model (mẫu — 1 giọng mặc định, api_key để trống) =====
DELETE FROM `ai_model_config` WHERE `id` = 'TTS_OriagentVoice';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_OriagentVoice', 'TTS', 'OriagentVoice', 'Voice Oriagent (realtime)', 0, 1,
'{"type":"oriagent_voice","api_url":"https://voice.oriagent.com/api/v1","voices":[{"name":"Giọng mặc định","language":"auto","api_key":""}]}',
'https://voice.oriagent.com', 'Oriagent VoxCPM Voice Clone — WebSocket realtime (mỗi API key một giọng)', 48, 1, NOW(), 1, NOW());

-- Dọn voice cũ của model mẫu (nếu còn sót từ bản REST trước) để backend tự sync lại theo voices.
DELETE FROM `ai_tts_voice` WHERE `tts_model_id` = 'TTS_OriagentVoice';
INSERT INTO `ai_tts_voice` (`id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_OriagentVoice0001', 'TTS_OriagentVoice', 'Giọng mặc định', 'Giọng mặc định', 'auto', NULL, NULL, 1, 1, NOW(), 1, NOW());
