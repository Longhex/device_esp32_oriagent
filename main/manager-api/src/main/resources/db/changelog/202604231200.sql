-- Add Blaze.vn TTS Provider (Standard HTTP)
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_Blaze';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_Blaze', 'TTS', 'blaze_http', 'Blaze.vn (Standard TTS)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (2.0_flash/2.0_pro)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"audio_speed","label":"Audio Speed (1)","type":"string"},{"key":"audio_quality","label":"Audio Quality (64)","type":"string"},{"key":"audio_format","label":"Format (wav/mp3)","type":"string"}]', 30, 1, NOW(), 1, NOW());

-- Add Blaze.vn TTS Stream Provider (WebSocket)
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_BlazeStream';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_BlazeStream', 'TTS', 'blaze_stream', 'Blaze.vn (Realtime TTS)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (2.0-realtime)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"audio_speed","label":"Audio Speed (1)","type":"string"}]', 31, 1, NOW(), 1, NOW());

-- Add Blaze.vn ASR Provider (Realtime WebSocket)
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_ASR_BlazeStream';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_ASR_BlazeStream', 'ASR', 'blaze_stream', 'Blaze.vn (Realtime ASR)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (v2.0)","type":"string"},{"key":"language","label":"Language (vi)","type":"string"}]', 32, 1, NOW(), 1, NOW());
