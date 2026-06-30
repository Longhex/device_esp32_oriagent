-- Register Qwen3 STT (internal) provider/model.
-- STT: qwen3_asr_vllm qua /api/internal/stt/test.
-- api_key để rỗng; nhập qua UI / set ở DB. Endpoint qwen3 là INTERNAL (phụ thuộc vLLM server bên họ).

-- ===== STT provider (Qwen3 - internal) =====
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_ASR_oriagent_qwen', 'ASR', 'oriagent_qwen', 'Oriagent Voice (Qwen3 STT - internal)',
'[{"key":"api_url","label":"URL API (mặc định: https://voice.oriagent.com/api/internal/stt/test)","type":"string"},{"key":"api_key","label":"API Key (Bearer Token)","type":"password"},{"key":"language","label":"Ngôn ngữ (vi / en / auto)","type":"string"},{"key":"provider","label":"Provider nội bộ (qwen3_asr_vllm)","type":"string"},{"key":"output_dir","label":"Thư mục output","type":"string"}]',
19, 1, NOW(), 1, NOW());

-- ===== STT model (Qwen3) =====
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('ASR_OriagentQwen', 'ASR', 'OriagentQwen', 'Oriagent Voice (Qwen3-ASR)', 0, 1,
'{"type":"oriagent_qwen","api_url":"https://voice.oriagent.com/api/internal/stt/test","api_key":"","language":"auto","provider":"qwen3_asr_vllm","output_dir":"tmp/"}',
'https://voice.oriagent.com', 'Qwen3-ASR qua endpoint internal (vLLM) - chữ có hoa/thường + dấu câu', 19, 1, NOW(), 1, NOW());
