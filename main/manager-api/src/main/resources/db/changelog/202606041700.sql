-- Register Oriagent self-hosted Voice (TTS + STT) providers and default models.
-- TTS: Piper via voice.oriagent.com /tts/generate (WAV 22050Hz mono)
-- STT: sherpa-onnx via voice.oriagent.com /stt/transcribe (WAV 16k mono)
-- API keys are left empty here on purpose; each agent/model fills its key in the UI.

-- ===== TTS provider =====
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_TTS_oriagent_voice', 'TTS', 'oriagent_voice', 'Oriagent Voice (TTS)',
'[{"key":"api_url","label":"URL API (mặc định: https://voice.oriagent.com/api/public/v1)","type":"string"},{"key":"api_key","label":"API Key (Bearer Token)","type":"password"},{"key":"voice","label":"Giọng đọc (vi-medium / lessac-medium / hfc_male-medium / vcctk-medium-p280)","type":"string"},{"key":"language","label":"Ngôn ngữ (vi / en)","type":"string"},{"key":"output_dir","label":"Thư mục output","type":"string"}]',
48, 1, NOW(), 1, NOW());

-- ===== TTS default model =====
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_OriagentVoice', 'TTS', 'OriagentVoice', 'Oriagent Voice (Tiếng Việt)', 0, 1,
'{"type":"oriagent_voice","api_url":"https://voice.oriagent.com/api/public/v1","api_key":"","voice":"vi-medium","language":"vi","format":"wav","output_dir":"tmp/"}',
'https://voice.oriagent.com', 'Oriagent self-hosted Piper TTS', 48, 1, NOW(), 1, NOW());

-- ===== TTS voices =====
INSERT IGNORE INTO `ai_tts_voice` (`id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('TTS_OriagentVoice0001', 'TTS_OriagentVoice', 'Oriagent-Tiếng Việt-vi-medium', 'vi-medium', 'Vietnamese', NULL, NULL, 1, 1, NOW(), 1, NOW()),
('TTS_OriagentVoice0002', 'TTS_OriagentVoice', 'Oriagent-English-lessac-medium', 'lessac-medium', 'English', NULL, NULL, 2, 1, NOW(), 1, NOW()),
('TTS_OriagentVoice0003', 'TTS_OriagentVoice', 'Oriagent-English-hfc_male-medium', 'hfc_male-medium', 'English', NULL, NULL, 3, 1, NOW(), 1, NOW()),
('TTS_OriagentVoice0004', 'TTS_OriagentVoice', 'Oriagent-English-vcctk-medium-p280', 'vcctk-medium-p280', 'English', NULL, NULL, 4, 1, NOW(), 1, NOW());

-- ===== STT (ASR) provider =====
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_ASR_oriagent_voice', 'ASR', 'oriagent_voice', 'Oriagent Voice (STT)',
'[{"key":"api_url","label":"URL API (mặc định: https://voice.oriagent.com/api/public/v1)","type":"string"},{"key":"api_key","label":"API Key (Bearer Token)","type":"password"},{"key":"language","label":"Ngôn ngữ (vi / en / auto)","type":"string"},{"key":"output_dir","label":"Thư mục output","type":"string"}]',
18, 1, NOW(), 1, NOW());

-- ===== STT (ASR) default model =====
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('ASR_OriagentVoice', 'ASR', 'OriagentVoice', 'Oriagent Voice (Tiếng Việt)', 0, 1,
'{"type":"oriagent_voice","api_url":"https://voice.oriagent.com/api/public/v1","api_key":"","language":"vi","output_dir":"tmp/"}',
'https://voice.oriagent.com', 'Oriagent self-hosted sherpa-onnx STT', 18, 1, NOW(), 1, NOW());
