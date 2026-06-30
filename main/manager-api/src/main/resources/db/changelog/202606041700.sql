-- Register Oriagent self-hosted Voice STT provider and default model.
-- STT: sherpa-onnx via voice.oriagent.com /stt/transcribe (WAV 16k mono)
-- API keys are left empty here on purpose; each agent/model fills its key in the UI.

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
