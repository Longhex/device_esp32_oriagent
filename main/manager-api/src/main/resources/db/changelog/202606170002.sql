-- Register oriagent_http provider + rename oriagent_ws + fix default model config types.
-- oriagent_ws  provider_code → Python type: oriagent_websocket (oriagent_websocket/oriagent_websocket.py)
-- oriagent_http provider_code → Python type: oriagent_http   (oriagent_http/oriagent_http.py)

-- 1. Rename existing oriagent_ws provider to "Oriagent (WS)"
UPDATE `ai_model_provider`
SET `name` = 'Oriagent (WS)'
WHERE `id` = 'SYSTEM_LLM_oriagent_ws';

-- 2. Register oriagent_http provider
INSERT IGNORE INTO `ai_model_provider`
    (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`)
VALUES (
    'SYSTEM_LLM_oriagent_http',
    'LLM',
    'oriagent_http',
    'Oriagent (HTTP)',
    '[{"key":"api_url","type":"string","label":"URL API (Dify/Oriagent)"},{"key":"api_key","type":"string","label":"API Key (Bearer Token)"},{"key":"model_name","type":"string","label":"Tên Model (Mặc định: oriagent-default)"}]',
    21
);

-- 3. Fix default Oriagent LLM config: type oriagent_ws → oriagent_http (HTTP SSE provider)
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.type', 'oriagent_http'),
    `model_name`  = 'Oriagent (HTTP)'
WHERE `id` = 'LLM_OriagentLLM';

-- 4. Add default Oriagent WebSocket LLM config (type: oriagent_websocket)
INSERT IGNORE INTO `ai_model_config`
    (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `sort`)
VALUES (
    'LLM_OriagentWS',
    'LLM',
    'OriagentWS',
    'Oriagent (WS)',
    0,
    1,
    '{"type":"oriagent_websocket","api_key":"your_api_key","api_url":"http://localhost:8080/v1/chat-messages","model_name":"oriagent-default"}',
    21
);
