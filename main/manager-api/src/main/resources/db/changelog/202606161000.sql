-- Register Oriagent Edge TTS (Microsoft Edge cloud) + Qwen3 STT (internal) providers/models.
-- TTS: edge-tts qua voice.oriagent.com /tts/generate (MP3). STT: qwen3_asr_vllm qua /api/internal/stt/test.
-- api_key để rỗng; nhập qua UI / set ở DB. Endpoint qwen3 là INTERNAL (phụ thuộc vLLM server bên họ).

-- ===== TTS provider (Edge) =====
INSERT IGNORE INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_TTS_oriagent_edge', 'TTS', 'oriagent_edge', 'Oriagent Voice (Edge TTS)',
'[{"key":"api_url","label":"URL API (mặc định: https://voice.oriagent.com/api/public/v1)","type":"string"},{"key":"api_key","label":"API Key (Bearer Token)","type":"password"},{"key":"voice","label":"Giọng đọc (nhãn Edge, vd en-US-AvaMultilingualNeural)","type":"string"},{"key":"language","label":"Ngôn ngữ mặc định (vi / en)","type":"string"},{"key":"model","label":"Model (edge-tts)","type":"string"},{"key":"format","label":"Định dạng (mp3)","type":"string"},{"key":"rate","label":"Tốc độ (vd +8%) - tùy chọn","type":"string"},{"key":"pitch","label":"Cao độ (vd +20Hz) - tùy chọn","type":"string"},{"key":"volume","label":"Âm lượng (vd +15%) - tùy chọn","type":"string"},{"key":"output_dir","label":"Thư mục output","type":"string"}]',
49, 1, NOW(), 1, NOW());

-- ===== TTS model (Edge) =====
INSERT IGNORE INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_OriagentEdge', 'TTS', 'OriagentEdge', 'Oriagent Voice (Edge - đa giọng)', 0, 1,
'{"type":"oriagent_edge","api_url":"https://voice.oriagent.com/api/public/v1","api_key":"","voice":"en-US-AvaMultilingualNeural","language":"en","model":"edge-tts","format":"mp3","output_dir":"tmp/"}',
'https://voice.oriagent.com', 'Microsoft Edge TTS qua Oriagent (cloud, nhiều giọng vi/en)', 49, 1, NOW(), 1, NOW());

-- ===== TTS voices (Edge vi + en) =====
INSERT IGNORE INTO `ai_tts_voice` (`id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('TTS_OriagentEdge0001', 'TTS_OriagentEdge', 'Edge-vi-VN-HoaiMyNeural', 'vi-VN-HoaiMyNeural', 'Vietnamese', NULL, NULL, 1, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0002', 'TTS_OriagentEdge', 'Edge-vi-VN-NamMinhNeural', 'vi-VN-NamMinhNeural', 'Vietnamese', NULL, NULL, 2, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0003', 'TTS_OriagentEdge', 'Edge-en-AU-NatashaNeural', 'en-AU-NatashaNeural', 'English', NULL, NULL, 3, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0004', 'TTS_OriagentEdge', 'Edge-en-AU-WilliamMultilingualNeural', 'en-AU-WilliamMultilingualNeural', 'English', NULL, NULL, 4, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0005', 'TTS_OriagentEdge', 'Edge-en-CA-ClaraNeural', 'en-CA-ClaraNeural', 'English', NULL, NULL, 5, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0006', 'TTS_OriagentEdge', 'Edge-en-CA-LiamNeural', 'en-CA-LiamNeural', 'English', NULL, NULL, 6, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0007', 'TTS_OriagentEdge', 'Edge-en-GB-LibbyNeural', 'en-GB-LibbyNeural', 'English', NULL, NULL, 7, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0008', 'TTS_OriagentEdge', 'Edge-en-GB-MaisieNeural', 'en-GB-MaisieNeural', 'English', NULL, NULL, 8, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0009', 'TTS_OriagentEdge', 'Edge-en-GB-RyanNeural', 'en-GB-RyanNeural', 'English', NULL, NULL, 9, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0010', 'TTS_OriagentEdge', 'Edge-en-GB-SoniaNeural', 'en-GB-SoniaNeural', 'English', NULL, NULL, 10, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0011', 'TTS_OriagentEdge', 'Edge-en-GB-ThomasNeural', 'en-GB-ThomasNeural', 'English', NULL, NULL, 11, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0012', 'TTS_OriagentEdge', 'Edge-en-HK-SamNeural', 'en-HK-SamNeural', 'English', NULL, NULL, 12, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0013', 'TTS_OriagentEdge', 'Edge-en-HK-YanNeural', 'en-HK-YanNeural', 'English', NULL, NULL, 13, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0014', 'TTS_OriagentEdge', 'Edge-en-IE-ConnorNeural', 'en-IE-ConnorNeural', 'English', NULL, NULL, 14, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0015', 'TTS_OriagentEdge', 'Edge-en-IE-EmilyNeural', 'en-IE-EmilyNeural', 'English', NULL, NULL, 15, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0016', 'TTS_OriagentEdge', 'Edge-en-IN-NeerjaExpressiveNeural', 'en-IN-NeerjaExpressiveNeural', 'English', NULL, NULL, 16, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0017', 'TTS_OriagentEdge', 'Edge-en-IN-NeerjaNeural', 'en-IN-NeerjaNeural', 'English', NULL, NULL, 17, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0018', 'TTS_OriagentEdge', 'Edge-en-IN-PrabhatNeural', 'en-IN-PrabhatNeural', 'English', NULL, NULL, 18, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0019', 'TTS_OriagentEdge', 'Edge-en-KE-AsiliaNeural', 'en-KE-AsiliaNeural', 'English', NULL, NULL, 19, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0020', 'TTS_OriagentEdge', 'Edge-en-KE-ChilembaNeural', 'en-KE-ChilembaNeural', 'English', NULL, NULL, 20, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0021', 'TTS_OriagentEdge', 'Edge-en-NG-AbeoNeural', 'en-NG-AbeoNeural', 'English', NULL, NULL, 21, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0022', 'TTS_OriagentEdge', 'Edge-en-NG-EzinneNeural', 'en-NG-EzinneNeural', 'English', NULL, NULL, 22, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0023', 'TTS_OriagentEdge', 'Edge-en-NZ-MitchellNeural', 'en-NZ-MitchellNeural', 'English', NULL, NULL, 23, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0024', 'TTS_OriagentEdge', 'Edge-en-NZ-MollyNeural', 'en-NZ-MollyNeural', 'English', NULL, NULL, 24, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0025', 'TTS_OriagentEdge', 'Edge-en-PH-JamesNeural', 'en-PH-JamesNeural', 'English', NULL, NULL, 25, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0026', 'TTS_OriagentEdge', 'Edge-en-PH-RosaNeural', 'en-PH-RosaNeural', 'English', NULL, NULL, 26, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0027', 'TTS_OriagentEdge', 'Edge-en-SG-LunaNeural', 'en-SG-LunaNeural', 'English', NULL, NULL, 27, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0028', 'TTS_OriagentEdge', 'Edge-en-SG-WayneNeural', 'en-SG-WayneNeural', 'English', NULL, NULL, 28, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0029', 'TTS_OriagentEdge', 'Edge-en-TZ-ElimuNeural', 'en-TZ-ElimuNeural', 'English', NULL, NULL, 29, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0030', 'TTS_OriagentEdge', 'Edge-en-TZ-ImaniNeural', 'en-TZ-ImaniNeural', 'English', NULL, NULL, 30, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0031', 'TTS_OriagentEdge', 'Edge-en-US-AnaNeural', 'en-US-AnaNeural', 'English', NULL, NULL, 31, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0032', 'TTS_OriagentEdge', 'Edge-en-US-AndrewMultilingualNeural', 'en-US-AndrewMultilingualNeural', 'English', NULL, NULL, 32, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0033', 'TTS_OriagentEdge', 'Edge-en-US-AndrewNeural', 'en-US-AndrewNeural', 'English', NULL, NULL, 33, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0034', 'TTS_OriagentEdge', 'Edge-en-US-AriaNeural', 'en-US-AriaNeural', 'English', NULL, NULL, 34, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0035', 'TTS_OriagentEdge', 'Edge-en-US-AvaMultilingualNeural', 'en-US-AvaMultilingualNeural', 'English', NULL, NULL, 35, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0036', 'TTS_OriagentEdge', 'Edge-en-US-AvaNeural', 'en-US-AvaNeural', 'English', NULL, NULL, 36, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0037', 'TTS_OriagentEdge', 'Edge-en-US-BrianMultilingualNeural', 'en-US-BrianMultilingualNeural', 'English', NULL, NULL, 37, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0038', 'TTS_OriagentEdge', 'Edge-en-US-BrianNeural', 'en-US-BrianNeural', 'English', NULL, NULL, 38, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0039', 'TTS_OriagentEdge', 'Edge-en-US-ChristopherNeural', 'en-US-ChristopherNeural', 'English', NULL, NULL, 39, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0040', 'TTS_OriagentEdge', 'Edge-en-US-EmmaMultilingualNeural', 'en-US-EmmaMultilingualNeural', 'English', NULL, NULL, 40, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0041', 'TTS_OriagentEdge', 'Edge-en-US-EmmaNeural', 'en-US-EmmaNeural', 'English', NULL, NULL, 41, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0042', 'TTS_OriagentEdge', 'Edge-en-US-EricNeural', 'en-US-EricNeural', 'English', NULL, NULL, 42, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0043', 'TTS_OriagentEdge', 'Edge-en-US-GuyNeural', 'en-US-GuyNeural', 'English', NULL, NULL, 43, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0044', 'TTS_OriagentEdge', 'Edge-en-US-JennyNeural', 'en-US-JennyNeural', 'English', NULL, NULL, 44, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0045', 'TTS_OriagentEdge', 'Edge-en-US-MichelleNeural', 'en-US-MichelleNeural', 'English', NULL, NULL, 45, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0046', 'TTS_OriagentEdge', 'Edge-en-US-RogerNeural', 'en-US-RogerNeural', 'English', NULL, NULL, 46, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0047', 'TTS_OriagentEdge', 'Edge-en-US-SteffanNeural', 'en-US-SteffanNeural', 'English', NULL, NULL, 47, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0048', 'TTS_OriagentEdge', 'Edge-en-ZA-LeahNeural', 'en-ZA-LeahNeural', 'English', NULL, NULL, 48, 1, NOW(), 1, NOW()),
('TTS_OriagentEdge0049', 'TTS_OriagentEdge', 'Edge-en-ZA-LukeNeural', 'en-ZA-LukeNeural', 'English', NULL, NULL, 49, 1, NOW(), 1, NOW());

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
