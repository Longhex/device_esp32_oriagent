import os
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.cache.manager import cache_manager, CacheType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

WEB_SEARCH_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Tìm kiếm thông tin thời gian thực trực tuyến. Thích hợp cho các câu hỏi cần sự thật mới nhất như giá cả, tin tức, chức vụ nhân vật, kết quả trận đấu, thay đổi chính sách, v.v."
            "Ưu tiên sử dụng khi câu hỏi của người dùng chứa các thông tin nhạy cảm về thời gian như hôm nay, mới nhất, bây giờ, thời gian thực, hiện tại, v.v."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi cần tìm kiếm, ví dụ: Giá vàng hôm nay, thời tiết TP.HCM, Chủ tịch nước Việt Nam là ai",
                },
                "count": {
                    "type": "integer",
                    "description": "Số lượng kết quả tìm kiếm, gợi ý từ 1 đến 5, mặc định là 3",
                },
                "deep_search": {
                    "type": "boolean",
                    "description": "Có đọc nội dung chi tiết và tổng hợp nhiều nguồn hay không, mặc định là false. Có thể đặt thành true cho các vấn đề phức tạp.",
                },
                "lang": {
                    "type": "string",
                    "description": "Mã ngôn ngữ người dùng, ví dụ: zh_CN/vi_VN/en_US, mặc định vi_VN",
                },
            },
            "required": ["query", "lang"],
        },
    },
}


def _build_proxies(proxy_url: str | None):
    if not proxy_url:
        return None
    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def _fetch_page_excerpt(url: str, timeout: float, source_chars: int, proxy_url: str | None):
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            },
            timeout=timeout,
            proxies=_build_proxies(proxy_url),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header"]):
            node.decompose()
        text = soup.get_text(separator="\n", strip=True)
        if not text:
            return f"SOURCE: {url}\n[Nội dung trống hoặc không thể phân tích]"
        return f"SOURCE: {url}\n{text[:source_chars]}..."
    except Exception as e:
        return f"SOURCE: {url}\n[Đọc thất bại: {str(e)}]"


@register_function("web_search", WEB_SEARCH_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def web_search(
    conn: "ConnectionHandler",
    query: str,
    count: int = 3,
    deep_search: bool = False,
    lang: str = "vi_VN",
):
    query = (query or "").strip()
    if not query:
        return ActionResponse(Action.ERROR, response="Từ khóa tìm kiếm không được để trống")

    plugin_config = conn.config.get("plugins", {}).get("web_search", {})
    region = plugin_config.get("region", "vn-vi")
    max_results = min(max(int(count or plugin_config.get("max_results", 3)), 1), 5)
    source_chars = int(plugin_config.get("source_chars", 2500))
    timeout = float(plugin_config.get("timeout", 10))
    proxy_url = plugin_config.get("proxy_url") or os.environ.get("SEARCH_PROXY")

    cache_key = f"{query}|{region}|{max_results}|{deep_search}|{source_chars}"
    cached = cache_manager.get(CacheType.INTENT, cache_key, namespace="web_search")
    if cached:
        return ActionResponse(Action.REQLLM, cached, None)

    try:
        with DDGS(proxy=proxy_url) as ddgs:
            results = list(
                ddgs.text(
                    query,
                    region=region,
                    safesearch="moderate",
                    timelimit="w",
                    max_results=max_results,
                )
            )
    except Exception as e:
        return ActionResponse(Action.ERROR, response=f"Tìm kiếm trực tuyến thất bại: {e}")

    if not results:
        return ActionResponse(
            Action.REQLLM,
            f"Không tìm thấy kết quả liên quan đến “{query}”, vui lòng nhắc người dùng thử lại với một từ khóa cụ thể hơn.",
            None,
        )

    lines = ["### BÁO CÁO TÌM KIẾM WEB ###", f"query: {query}", f"lang: {lang}"]
    for idx, item in enumerate(results, start=1):
        lines.append(f"\n[{idx}] {item.get('title', 'Tiêu đề không xác định')}")
        lines.append(f"URL: {item.get('href', '')}")
        if item.get("body"):
            lines.append(f"Tóm tắt: {item.get('body')}")

    if deep_search:
        lines.append("\n### DEEP SEARCH SOURCES ###")
        for item in results:
            href = item.get("href")
            if href:
                lines.append(_fetch_page_excerpt(href, timeout, source_chars, proxy_url))

    report = "\n".join(lines)
    cache_manager.set(CacheType.INTENT, cache_key, report, namespace="web_search")

    prompt = (
        f"Vui lòng trả lời câu hỏi của người dùng bằng ngôn ngữ {lang} dựa trên kết quả tìm kiếm trực tuyến sau đây.\n"
        f"Câu hỏi của người dùng: {query}\n\n"
        f"{report}\n\n"
        "Yêu cầu: 1. Đưa ra kết luận trước; 2. Nêu rõ đây là kết quả tìm kiếm trực tuyến;"
        "3. Nếu kết quả có thể thay đổi theo thời gian, vui lòng nhắc người dùng đây là thông tin tìm kiếm được tại thời điểm hiện tại;"
        "4. Nếu các nguồn không nhất quán, vui lòng chỉ ra sự khác biệt."
    )
    return ActionResponse(Action.REQLLM, prompt, None)
