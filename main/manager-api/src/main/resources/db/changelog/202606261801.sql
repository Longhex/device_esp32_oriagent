-- Add Blaze.vn TTS V4 Provider (Opus-Direct + Parallel Pool)
-- type 'blaze_speed_v4' -> core/providers/tts/blaze_speed_v4.py
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_BlazeSpeedV4';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_BlazeSpeedV4', 'TTS', 'blaze_speed_v4', 'Blaze.vn (Speed V4)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (2.0-realtime)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"audio_speed","label":"Audio Speed (1.2)","type":"string"},{"key":"audio_quality","label":"Audio Quality (32/64/128)","type":"number"}]', 36, 1, NOW(), 1, NOW());
