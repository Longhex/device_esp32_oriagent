# Compat shim: provider "oriagent_ws" đã được đổi tên thành "oriagent_http" (khi merge main).
# Nhưng một số config/DB/cache cũ vẫn dùng type "oriagent_ws". Re-export LLMProvider của
# oriagent_http để type "oriagent_ws" vẫn nạp được (tránh lỗi "不支持的LLM类型: oriagent_ws").
from core.providers.llm.oriagent_http.oriagent_http import LLMProvider  # noqa: F401
