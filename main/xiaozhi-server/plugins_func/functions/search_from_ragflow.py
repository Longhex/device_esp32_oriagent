import requests
import sys
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

# 定义基础的函数描述模板
SEARCH_FROM_RAGFLOW_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "search_from_ragflow",
        "description": "Truy vấn thông tin từ cơ sở kiến thức (knowledge base)",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "Câu hỏi cần truy vấn"}},
            "required": ["question"],
        },
    },
}


@register_function(
    "search_from_ragflow", SEARCH_FROM_RAGFLOW_FUNCTION_DESC, ToolType.SYSTEM_CTL
)
def search_from_ragflow(conn: "ConnectionHandler", question=None):
    # 确保字符串参数正确处理编码
    if question and isinstance(question, str):
        # 确保问题参数是UTF-8编码的字符串
        pass
    else:
        question = str(question) if question is not None else ""

    ragflow_config = conn.config.get("plugins", {}).get("search_from_ragflow", {})
    base_url = ragflow_config.get("base_url", "")
    api_key = ragflow_config.get("api_key", "")
    dataset_ids = ragflow_config.get("dataset_ids", [])

    url = base_url + "/api/v1/retrieval"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 确保payload中的字符串都是UTF-8编码
    payload = {"question": question, "dataset_ids": dataset_ids}

    try:
        # 使用ensure_ascii=False确保JSON序列化时正确处理中文
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=5,
            verify=False,
        )

        # 显式设置响应的编码为utf-8
        response.encoding = "utf-8"

        response.raise_for_status()

        # 先获取文本内容，然后手动处理JSON解码
        response_text = response.text
        import json

        result = json.loads(response_text)

        if result.get("code") != 0:
            error_detail = result.get("error", {}).get("detail", "未知错误")
            error_message = result.get("error", {}).get("message", "")
            error_code = result.get("code", "")

            # 安全地记录错误信息
            logger.bind(tag=TAG).error(
                f"RAGFlow API call failed, code: {error_code}, detail: {error_detail}, response: {result}"
            )

            # 构建详细的错误响应
            error_response = f"RAG interface returned exception (Error code: {error_code})"

            if error_message:
                error_response += f": {error_message}"
            if error_detail:
                error_response += f"\nChi tiết: {error_detail}"

            return ActionResponse(Action.RESPONSE, None, error_response)

        chunks = result.get("data", {}).get("chunks", [])
        contents = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if content:
                # 安全地处理内容字符串
                if isinstance(content, str):
                    contents.append(content)
                elif isinstance(content, bytes):
                    contents.append(content.decode("utf-8", errors="replace"))
                else:
                    contents.append(str(content))

        if contents:
            # 组织知识库内容为引用模式
            context_text = f"# Về câu hỏi 【{question}】 đã tìm thấy kiến thức như sau:\n"
            context_text += "```\n\n\n".join(contents[:5])
            context_text += "\n```"
        else:
            context_text = "Dựa trên kết quả truy vấn cơ sở kiến thức, không tìm thấy thông tin liên quan."
        return ActionResponse(Action.REQLLM, context_text, None)

    except requests.exceptions.RequestException as e:
        # 网络请求异常
        error_type = type(e).__name__
        logger.bind(tag=TAG).error(
            f"RAGflow network request failed, type: {error_type}, detail: {str(e)}"
        )

        # 根据异常类型提供更详细的错误信息和解决方案
        if isinstance(e, requests.exceptions.ConnectTimeout):
            error_response = "Kết nối RAG interface quá hạn (5 giây)"
            error_response += "\nNguyên nhân có thể: Dịch vụ RAGflow chưa khởi động hoặc lỗi mạng"
            error_response += "\nGiải pháp: Vui lòng kiểm tra trạng thái dịch vụ RAGflow và kết nối mạng"

        elif isinstance(e, requests.exceptions.ConnectionError):
            error_response = "Không thể kết nối tới RAG interface"
            error_response += "\nNguyên nhân có thể: Địa chỉ dịch vụ RAGflow sai hoặc dịch vụ chưa chạy"
            error_response += "\nGiải pháp: Vui lòng kiểm tra cấu hình địa chỉ và trạng thái dịch vụ RAGflow"

        elif isinstance(e, requests.exceptions.Timeout):
            error_response = "Yêu cầu RAG interface quá hạn"
            error_response += "\nNguyên nhân có thể: Dịch vụ RAGflow phản hồi chậm hoặc lag mạng"
            error_response += "\nGiải pháp: Vui lòng thử lại sau hoặc kiểm tra hiệu năng dịch vụ RAGflow"

        elif isinstance(e, requests.exceptions.HTTPError):
            # 处理HTTP错误状态码
            if hasattr(e.response, "status_code"):
                status_code = e.response.status_code
                error_response = f"Lỗi HTTP RAG interface (Mã trạng thái: {status_code})"

                # 尝试获取响应内容中的错误信息
                try:
                    error_detail = e.response.json().get("error", {}).get("message", "")
                    if error_detail:
                        error_response += f"\nChi tiết lỗi: {error_detail}"
                except:
                    pass
            else:
                error_response = f"Ngoại lệ HTTP RAG interface: {str(e)}"

        else:
            error_response = f"Ngoại lệ mạng RAG interface ({error_type}): {str(e)}"

        return ActionResponse(Action.RESPONSE, None, error_response)

    except Exception as e:
        # 其他异常
        error_type = type(e).__name__
        logger.bind(tag=TAG).error(
            f"RAGflow processing exception, type: {error_type}, detail: {str(e)}"
        )

        # 提供详细的错误信息
        error_response = f"Ngoại lệ xử lý RAG interface ({error_type}): {str(e)}"
        return ActionResponse(Action.RESPONSE, None, error_response)
