-- Rename existing providers to English
UPDATE `ai_model_provider` SET `name` = 'FunASR (Local)' WHERE `provider_code` = 'fun_local';
UPDATE `ai_model_provider` SET `name` = 'FunASR Server' WHERE `provider_code` = 'fun_server';
UPDATE `ai_model_provider` SET `name` = 'Sherpa ASR' WHERE `provider_code` = 'sherpa_onnx_local';
UPDATE `ai_model_provider` SET `name` = 'Doubao ASR' WHERE `provider_code` = 'doubao';
UPDATE `ai_model_provider` SET `name` = 'Doubao Stream ASR' WHERE `provider_code` = 'doubao_stream';
UPDATE `ai_model_provider` SET `name` = 'Tencent ASR' WHERE `provider_code` = 'tencent' AND `model_type` = 'ASR';
UPDATE `ai_model_provider` SET `name` = 'Aliyun ASR' WHERE `provider_code` = 'aliyun' AND `model_type` = 'ASR';
UPDATE `ai_model_provider` SET `name` = 'Aliyun Stream ASR' WHERE `provider_code` = 'aliyun_stream' AND `model_type` = 'ASR';
UPDATE `ai_model_provider` SET `name` = 'Baidu ASR' WHERE `provider_code` = 'baidu';
UPDATE `ai_model_provider` SET `name` = 'OpenAI ASR' WHERE `provider_code` = 'openai' AND `model_type` = 'ASR';
UPDATE `ai_model_provider` SET `name` = 'Vosk ASR' WHERE `provider_code` = 'vosk';
UPDATE `ai_model_provider` SET `name` = 'Qwen ASR Flash' WHERE `provider_code` = 'qwen3_asr_flash';
UPDATE `ai_model_provider` SET `name` = 'Xunfei Stream ASR' WHERE `provider_code` = 'xunfei_stream' AND `model_type` = 'ASR';
UPDATE `ai_model_provider` SET `name` = 'Aliyun BL Stream ASR' WHERE `provider_code` = 'aliyunbl_stream' AND `model_type` = 'ASR';

UPDATE `ai_model_provider` SET `name` = 'Edge TTS' WHERE `provider_code` = 'edge';
UPDATE `ai_model_provider` SET `name` = 'Doubao TTS' WHERE `provider_code` = 'doubao' AND `model_type` = 'TTS';
UPDATE `ai_model_provider` SET `name` = 'Huoshan TTS (Double Stream)' WHERE `provider_code` = 'huoshan_double_stream';
UPDATE `ai_model_provider` SET `name` = 'SiliconFlow TTS' WHERE `provider_code` = 'siliconflow';
UPDATE `ai_model_provider` SET `name` = 'Coze TTS' WHERE `provider_code` = 'cozecn';
UPDATE `ai_model_provider` SET `name` = 'Volcengine Gateway TTS' WHERE `provider_code` = 'openai' AND `id` = 'SYSTEM_TTS_VolcesAiGatewayTTS';
UPDATE `ai_model_provider` SET `name` = 'Fish Speech' WHERE `provider_code` = 'fishspeech';
UPDATE `ai_model_provider` SET `name` = 'GPT-SoVITS V2' WHERE `provider_code` = 'gpt_sovits_v2';
UPDATE `ai_model_provider` SET `name` = 'MiniMax HTTP Stream TTS' WHERE `provider_code` = 'minimax_httpstream';
UPDATE `ai_model_provider` SET `name` = 'Aliyun TTS' WHERE `provider_code` = 'aliyun' AND `model_type` = 'TTS';
UPDATE `ai_model_provider` SET `name` = 'Aliyun Stream TTS' WHERE `provider_code` = 'aliyun_stream' AND `model_type` = 'TTS';
UPDATE `ai_model_provider` SET `name` = 'Tencent TTS' WHERE `provider_code` = 'tencent' AND `model_type` = 'TTS';
UPDATE `ai_model_provider` SET `name` = '302.AI TTS' WHERE `provider_code` = 'doubao' AND `id` = 'SYSTEM_TTS_TTS302AI';
UPDATE `ai_model_provider` SET `name` = 'OpenAI TTS' WHERE `provider_code` = 'openai' AND `model_type` = 'TTS';
UPDATE `ai_model_provider` SET `name` = 'Linkerai TTS' WHERE `provider_code` = 'linkerai';
UPDATE `ai_model_provider` SET `name` = 'Xunfei Stream TTS' WHERE `provider_code` = 'xunfei_stream' AND `model_type` = 'TTS';

-- Add New ASR Provider: Deepgram
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_ASR_Deepgram';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_ASR_Deepgram', 'ASR', 'deepgram', 'Deepgram (Nova-2 Stream)', '[{"key":"api_key","label":"API Key","type":"string"},{"key":"model","label":"Model (e.g. nova-2)","type":"string"},{"key":"language","label":"Language (e.g. vi)","type":"string"},{"key":"smart_format","label":"Smart Format","type":"string"},{"key":"filler_words","label":"Filler Words","type":"string"},{"key":"interim_results","label":"Interim Results","type":"string"},{"key":"utterance_end_ms","label":"Utterance End (ms)","type":"string"},{"key":"vad_events","label":"VAD Events","type":"string"},{"key":"endpointing","label":"Endpointing (ms)","type":"string"},{"key":"output_dir","label":"Output Directory","type":"string"}]', 20, 1, NOW(), 1, NOW());

-- Add New TTS Provider: Cartesia
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_Cartesia';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_Cartesia', 'TTS', 'cartesia', 'Cartesia (Sonic Stream)', '[{"key":"api_key","label":"API Key","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"model","label":"Model (e.g. sonic-english)","type":"string"},{"key":"sample_rate","label":"Sample Rate (Hz)","type":"string"}]', 21, 1, NOW(), 1, NOW());

-- Add New TTS Provider: Murf Falcon
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_MurfFalcon';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_MurfFalcon', 'TTS', 'murf_falcon', 'Murf AI (Falcon Stream)', '[{"key":"api_key","label":"API Key","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"model","label":"Model (e.g. FALCON)","type":"string"},{"key":"sample_rate","label":"Sample Rate (Hz)","type":"string"},{"key":"locale","label":"Locale (e.g. en-US)","type":"string"}]', 22, 1, NOW(), 1, NOW());

-- Add New TTS Provider: MiniMax Stream
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_MiniMaxStream';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_MiniMaxStream', 'TTS', 'minimax_stream', 'MiniMax (V2 Stream)', '[{"key":"api_key","label":"API Key","type":"string"},{"key":"domain","label":"Domain (api.minimax.io)","type":"string"},{"key":"model","label":"Model (speech-2.8-turbo)","type":"string"},{"key":"voice","label":"Voice ID","type":"string"},{"key":"sample_rate","label":"Sample Rate (Hz)","type":"string"}]', 23, 1, NOW(), 1, NOW());

-- Add New TTS Provider: Deepgram Aura
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_DeepgramAura';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_DeepgramAura', 'TTS', 'deepgram_aura', 'Deepgram (Aura Stream)', '[{"key":"api_key","label":"API Key","type":"string"},{"key":"model","label":"Model (aura-asteria-en)","type":"string"},{"key":"encoding","label":"Encoding (linear16)","type":"string"},{"key":"sample_rate","label":"Sample Rate (Hz)","type":"string"}]', 24, 1, NOW(), 1, NOW());
