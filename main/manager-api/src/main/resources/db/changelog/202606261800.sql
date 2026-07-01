-- Thinking-buffer (câu đệm suy nghĩ) — per-agent fields + global defaults.
-- Áp dụng TOÀN HỆ THỐNG (mọi TTS provider), engine xử lý ở xiaozhi-server.

-- 1) Per-agent: cấu hình riêng từng agent (NULL = theo mặc định toàn cục).
ALTER TABLE `ai_agent`
    ADD COLUMN `filler_enabled` tinyint(1) DEFAULT NULL
        COMMENT 'Câu đệm suy nghĩ: 1=bật, 0=tắt, NULL=theo mặc định toàn cục'
        AFTER `oriagent_model_name`;
ALTER TABLE `ai_agent`
    ADD COLUMN `filler_delay_ms` int DEFAULT NULL
        COMMENT 'Câu đệm: thời gian đợi (ms) trước khi phát'
        AFTER `filler_enabled`;
ALTER TABLE `ai_agent`
    ADD COLUMN `filler_phrases` text
        COMMENT 'Câu đệm: danh sách câu (mỗi câu 1 dòng hoặc ngăn bằng |)'
        AFTER `filler_delay_ms`;

-- 2) Default toàn cục (sys_params) — nested dưới key filler_default.* khi serve.
INSERT INTO `sys_params` (id, param_code, param_value, value_type, param_type, remark) VALUES
    (503, 'filler_default.enabled', 'false', 'boolean', 1, 'Câu đệm suy nghĩ - bật/tắt mặc định toàn hệ thống');
INSERT INTO `sys_params` (id, param_code, param_value, value_type, param_type, remark) VALUES
    (504, 'filler_default.delay_ms', '700', 'number', 1, 'Câu đệm - thời gian đợi mặc định (ms)');
INSERT INTO `sys_params` (id, param_code, param_value, value_type, param_type, remark) VALUES
    (505, 'filler_default.phrases', 'Ừm, để mình nghĩ xíu nha|Câu này hay nè, đợi mình một chút|Để mình xem nào|Hmm, thú vị đấy, chờ mình tí nhé', 'string', 1, 'Câu đệm - danh sách câu mặc định (ngăn bằng |)');
