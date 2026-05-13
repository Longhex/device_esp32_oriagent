-- Add Blaze.vn TTS V3 Provider (Per-request WS + Raw PCM Streaming)
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_BlazeSpeedV3';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_BlazeSpeedV3', 'TTS', 'blaze_speed_v3', 'Blaze.vn (Speed V3)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (2.0-realtime)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"audio_speed","label":"Audio Speed (1)","type":"string"}]', 35, 1, NOW(), 1, NOW());
