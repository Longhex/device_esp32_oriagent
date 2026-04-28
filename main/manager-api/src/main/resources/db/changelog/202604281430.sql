-- Add Blaze.vn TTS Super Speed Provider
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_BlazeSpeed';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_BlazeSpeed', 'TTS', 'blaze_speed', 'Blaze.vn (Super Speed TTS)', '[{"key":"api_key","label":"API Token","type":"string"},{"key":"model","label":"Model (2.0-realtime)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"audio_speed","label":"Audio Speed (1.2)","type":"string"}]', 33, 1, NOW(), 1, NOW());
