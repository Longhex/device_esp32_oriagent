-- Sau khi đổi tên LLM provider oriagent_ws -> oriagent_http (module oriagent_ws đã bị xóa),
-- migrate cấu hình DB để các model/agent đang dùng type "oriagent_ws" không bị chết khi tải provider.
-- oriagent_http là bản đổi tên trực tiếp của oriagent_ws (cùng Dify HTTP chat-messages).

UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.type', 'oriagent_http')
WHERE `model_type` = 'LLM'
  AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.type')) = 'oriagent_ws';
