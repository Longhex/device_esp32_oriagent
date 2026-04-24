import random
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler


TAG = __name__
logger = setup_logging()

GET_NEWS_FROM_CHINANEWS_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news_from_chinanews",
        "description": (
            "Lấy tin tức mới nhất và chọn ngẫu nhiên một tin để thông báo."
            "Người dùng có thể chỉ định loại tin tức, như tin tức xã hội, tin tức công nghệ, tin tức quốc tế, v.v."
            "Nếu không chỉ định, mặc định thông báo tin tức xã hội."
            "Người dùng có thể yêu cầu lấy nội dung chi tiết, khi đó sẽ lấy nội dung chi tiết của tin tức."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Danh mục tin tức, ví dụ: xã hội, công nghệ, quốc tế. Tham số tùy chọn, nếu không cung cấp sẽ dùng danh mục mặc định",
                },
                "detail": {
                    "type": "boolean",
                    "description": "Có lấy nội dung chi tiết hay không, mặc định là false. Nếu là true, sẽ lấy nội dung chi tiết của tin tức trước đó",
                },
                "lang": {
                    "type": "string",
                    "description": "Mã ngôn ngữ người dùng, ví dụ: zh_CN/vi_VN/en_US, mặc định vi_VN",
                },
            },
            "required": ["lang"],
        },
    },
}


def fetch_news_from_rss(rss_url):
    """从RSS源获取新闻列表"""
    try:
        response = requests.get(rss_url)
        response.raise_for_status()

        # 解析XML
        root = ET.fromstring(response.content)

        # 查找所有item元素（新闻条目）
        news_items = []
        for item in root.findall(".//item"):
            title = (
                item.find("title").text if item.find("title") is not None else "Không có tiêu đề"
            )
            link = item.find("link").text if item.find("link") is not None else "#"
            description = (
                item.find("description").text
                if item.find("description") is not None
                else "Không có mô tả"
            )
            pubDate = (
                item.find("pubDate").text
                if item.find("pubDate") is not None
                else "Thời gian không xác định"
            )

            news_items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pubDate": pubDate,
                }
            )

        return news_items
    except Exception as e:
        logger.bind(tag=TAG).error(f"Failed to fetch RSS news: {e}")
        return []


def fetch_news_detail(url):
    """获取新闻详情页内容并总结"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # 尝试提取正文内容 (这里的选择器需要根据实际网站结构调整)
        content_div = soup.select_one(
            ".content_desc, .content, article, .article-content"
        )
        if content_div:
            paragraphs = content_div.find_all("p")
            content = "\n".join(
                [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
            )
            return content
        else:
            # 如果找不到特定的内容区域，尝试获取所有段落
            paragraphs = soup.find_all("p")
            content = "\n".join(
                [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
            )
            return content[:2000]  # 限制长度
    except Exception as e:
        logger.bind(tag=TAG).error(f"Failed to fetch news detail: {e}")
        return "Không thể lấy nội dung chi tiết"


def map_category(category_text):
    """将用户输入的中文类别映射到配置文件中的类别键"""
    if not category_text:
        return None

    # 类别映射字典，目前支持社会、国际、财经新闻，如需更多类型，参见配置文件
    category_map = {
        # 社会新闻
        "xã hội": "society_rss_url",
        "tin xã hội": "society_rss_url",
        # 国际新闻
        "quốc tế": "world_rss_url",
        "tin quốc tế": "world_rss_url",
        # 财经新闻
        "tài chính": "finance_rss_url",
        "tin tài chính": "finance_rss_url",
        "kinh tế": "finance_rss_url",
    }

    # 转换为小写并去除空格
    normalized_category = category_text.lower().strip()

    # 返回映射结果，如果没有匹配项则返回原始输入
    return category_map.get(normalized_category, category_text)


@register_function(
    "get_news_from_chinanews",
    GET_NEWS_FROM_CHINANEWS_FUNCTION_DESC,
    ToolType.SYSTEM_CTL,
)
def get_news_from_chinanews(
    conn: "ConnectionHandler",
    category: str = None,
    detail: bool = False,
    lang: str = "vi_VN",
):
    """获取新闻并随机选择一条进行播报，或获取上一条新闻的详细内容"""
    try:
        # 如果detail为True，获取上一条新闻的详细内容
        if detail:
            if (
                not hasattr(conn, "last_news_link")
                or not conn.last_news_link
                or "link" not in conn.last_news_link
            ):
                return ActionResponse(
                    Action.REQLLM,
                    "Rất tiếc, không tìm thấy tin tức đã truy vấn gần đây, vui lòng lấy một tin tức trước.",
                    None,
                )

            link = conn.last_news_link.get("link")
            title = conn.last_news_link.get("title", "未知标题")

            if link == "#":
                return ActionResponse(
                    Action.REQLLM, "Rất tiếc, tin tức này không có liên kết khả dụng để lấy nội dung chi tiết.", None
                )

            logger.bind(tag=TAG).debug(f"获取新闻详情: {title}, URL={link}")

            # 获取新闻详情
            detail_content = fetch_news_detail(link)

            if not detail_content or detail_content == "Không thể lấy nội dung chi tiết":
                return ActionResponse(
                    Action.REQLLM,
                    f"Rất tiếc, không thể lấy nội dung chi tiết của 《{title}》, có thể liên kết đã hết hạn hoặc cấu trúc trang web đã thay đổi.",
                    None,
                )

            # 构建详情报告
            detail_report = (
                f"Dựa trên dữ liệu sau, dùng ngôn ngữ {lang} để trả lời yêu cầu truy vấn chi tiết tin tức của người dùng：\n\n"
                f"Tiêu đề tin tức: {title}\n"
                f"Nội dung chi tiết: {detail_content}\n\n"
                f"(Vui lòng tóm tắt nội dung tin tức trên, trích xuất các thông tin chính, thông báo cho người dùng một cách tự nhiên và trôi chảy, "
                f"đừng đề cập rằng đây là bản tóm tắt, hãy giống như đang kể một câu chuyện tin tức hoàn chỉnh)"
            )

            return ActionResponse(Action.REQLLM, detail_report, None)

        # 否则，获取新闻列表并随机选择一条
        # 从配置中获取RSS URL
        rss_config = conn.config.get("plugins", {}).get("get_news_from_chinanews", {})
        default_rss_url = rss_config.get(
            "default_rss_url", "https://www.chinanews.com.cn/rss/society.xml"
        )

        # 将用户输入的类别映射到配置中的类别键
        mapped_category = map_category(category)

        # 如果提供了类别，尝试从配置中获取对应的URL
        rss_url = default_rss_url
        if mapped_category and mapped_category in rss_config:
            rss_url = rss_config[mapped_category]

        logger.bind(tag=TAG).info(
            f"获取新闻: 原始类别={category}, 映射类别={mapped_category}, URL={rss_url}"
        )

        # 获取新闻列表
        news_items = fetch_news_from_rss(rss_url)

        if not news_items:
            return ActionResponse(
                Action.REQLLM, "Rất tiếc, không thể lấy thông tin tin tức, vui lòng thử lại sau.", None
            )

        # 随机选择一条新闻
        selected_news = random.choice(news_items)

        # 保存当前新闻链接到连接对象，以便后续查询详情
        if not hasattr(conn, "last_news_link"):
            conn.last_news_link = {}
        conn.last_news_link = {
            "link": selected_news.get("link", "#"),
            "title": selected_news.get("title", "Không có tiêu đề"),
        }

        # 构建新闻报告
        news_report = (
            f"Dựa trên dữ liệu sau, dùng ngôn ngữ {lang} để trả lời yêu cầu truy vấn tin tức của người dùng：\n\n"
            f"Tiêu đề tin tức: {selected_news['title']}\n"
            f"Thời gian phát hành: {selected_news['pubDate']}\n"
            f"Nội dung tin tức: {selected_news['description']}\n"
            f"(Vui lòng thông báo tin tức này cho người dùng một cách tự nhiên và trôi chảy, có thể tóm tắt nội dung phù hợp, "
            f"đọc trực tiếp tin tức, không cần thêm nội dung dư thừa. "
            f"Nếu người dùng yêu cầu biết thêm chi tiết, hãy nói rằng người dùng có thể nói 'Hãy giới thiệu chi tiết tin tức này' để biết thêm thông tin)"
        )

        return ActionResponse(Action.REQLLM, news_report, None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"Error fetching news: {e}")
        return ActionResponse(
            Action.REQLLM, "Rất tiếc, đã xảy ra lỗi khi lấy tin tức, vui lòng thử lại sau.", None
        )
