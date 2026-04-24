import random
import requests
import json
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from markitdown import MarkItDown
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler


TAG = __name__
logger = setup_logging()

CHANNEL_MAP = {
    "V2EX": "v2ex-share",
    "知乎": "zhihu",
    "微博": "weibo",
    "联合早报": "zaobao",
    "酷安": "coolapk",
    "MKTNews": "mktnews-flash",
    "华尔街见闻": "wallstreetcn-quick",
    "36氪": "36kr-quick",
    "抖音": "douyin",
    "虎扑": "hupu",
    "百度贴吧": "tieba",
    "今日头条": "toutiao",
    "IT之家": "ithome",
    "澎湃新闻": "thepaper",
    "卫星通讯社": "sputniknewscn",
    "参考消息": "cankaoxiaoxi",
    "远景论坛": "pcbeta-windows11",
    "财联社": "cls-depth",
    "雪球": "xueqiu-hotstock",
    "格隆汇": "gelonghui",
    "法布财经": "fastbull-express",
    "Solidot": "solidot",
    "Hacker News": "hackernews",
    "Product Hunt": "producthunt",
    "Github": "github-trending-today",
    "哔哩哔哩": "bilibili-hot-search",
    "快手": "kuaishou",
    "靠谱新闻": "kaopu",
    "金十数据": "jin10",
    "百度热搜": "baidu",
    "牛客": "nowcoder",
    "少数派": "sspai",
    "稀土掘金": "juejin",
    "凤凰网": "ifeng",
    "虫部落": "chongbuluo-latest",
}


# 默认新闻来源字典，当配置中没有指定时使用
DEFAULT_NEWS_SOURCES = "澎湃新闻;百度热搜;财联社"


def get_news_sources_from_config(conn):
    """从配置中获取新闻源字符串"""
    try:
        # 尝试从插件配置中获取新闻源
        if (
            conn.config.get("plugins")
            and conn.config["plugins"].get("get_news_from_newsnow")
            and conn.config["plugins"]["get_news_from_newsnow"].get("news_sources")
        ):
            # 获取配置的新闻源字符串
            news_sources_config = conn.config["plugins"]["get_news_from_newsnow"][
                "news_sources"
            ]

            if isinstance(news_sources_config, str) and news_sources_config.strip():
                logger.bind(tag=TAG).debug(f"使用配置的新闻源: {news_sources_config}")
                return news_sources_config
            else:
                logger.bind(tag=TAG).warning("新闻源配置为空或格式错误，使用默认配置")
        else:
            logger.bind(tag=TAG).debug("未找到新闻源配置，使用默认配置")

        return DEFAULT_NEWS_SOURCES

    except Exception as e:
        logger.bind(tag=TAG).error(f"获取新闻源配置失败: {e}，使用默认配置")
        return DEFAULT_NEWS_SOURCES


# 从CHANNEL_MAP获取所有可用的新闻源名称
available_sources = list(CHANNEL_MAP.keys())
example_sources_str = "、".join(available_sources)

GET_NEWS_FROM_NEWSNOW_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news_from_newsnow",
        "description": (
            "Lấy tin tức mới nhất và chọn ngẫu nhiên một tin để thông báo."
            f"Người dùng có thể chọn các nguồn tin tức khác nhau, tên tiêu chuẩn là: {example_sources_str}"
            "Ví dụ nếu người dùng yêu cầu tin tức Baidu, thực chất là Baidu Hot Search. Nếu không chỉ định, mặc định lấy từ The Paper (Bành Phái)."
            "Người dùng có thể yêu cầu lấy nội dung chi tiết, khi đó sẽ lấy nội dung chi tiết của tin tức."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": f"Tên tiếng Trung tiêu chuẩn của nguồn tin tức, ví dụ {example_sources_str}, v.v. Tham số tùy chọn, nếu không cung cấp sẽ dùng nguồn mặc định",
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


def fetch_news_from_api(conn: "ConnectionHandler", source="thepaper"):
    """从API获取新闻列表"""
    try:
        api_url = f"https://newsnow.busiyi.world/api/s?id={source}"

        news_config = conn.config.get("plugins", {}).get("get_news_from_newsnow", {})
        if news_config.get("url"):
            api_url = news_config["url"] + source

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if "items" in data:
            return data["items"]
        else:
            logger.bind(tag=TAG).error(f"获取新闻API响应格式错误: {data}")
            return []

    except Exception as e:
        logger.bind(tag=TAG).error(f"获取新闻API失败: {e}")
        return []


def fetch_news_detail(url):
    """获取新闻详情页内容并使用MarkItDown清理HTML"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # 使用MarkItDown清理HTML内容
        md = MarkItDown(enable_plugins=False)
        result = md.convert(response)

        # 获取清理后的文本内容
        clean_text = result.text_content

        # 如果清理后的内容为空，返回提示信息
        if not clean_text or len(clean_text.strip()) == 0:
            logger.bind(tag=TAG).warning(f"清理后的新闻内容为空: {url}")
            return "无法解析新闻详情内容，可能是网站结构特殊或内容受限。"

        return clean_text
    except Exception as e:
        logger.bind(tag=TAG).error(f"获取新闻详情失败: {e}")
        return "无法获取详细内容"


@register_function(
    "get_news_from_newsnow",
    GET_NEWS_FROM_NEWSNOW_FUNCTION_DESC,
    ToolType.SYSTEM_CTL,
)
def get_news_from_newsnow(
    conn: "ConnectionHandler",
    source: str = "澎湃新闻",
    detail: bool = False,
    lang: str = "zh_CN",
):
    """获取新闻并随机选择一条进行播报，或获取上一条新闻的详细内容"""
    try:
        # 获取当前配置的新闻源
        news_sources = get_news_sources_from_config(conn)

        # 如果detail为True，获取上一条新闻的详细内容
        detail = str(detail).lower() == "true"
        if detail:
            if (
                not hasattr(conn, "last_newsnow_link")
                or not conn.last_newsnow_link
                or "url" not in conn.last_newsnow_link
            ):
                return ActionResponse(
                    Action.REQLLM,
                    "Rất tiếc, không tìm thấy tin tức đã truy vấn gần đây, vui lòng lấy một tin tức trước.",
                    None,
                )

            url = conn.last_newsnow_link.get("url")
            title = conn.last_newsnow_link.get("title", "未知标题")
            source_id = conn.last_newsnow_link.get("source_id", "thepaper")
            source_name = CHANNEL_MAP.get(source_id, "未知来源")

            if not url or url == "#":
                return ActionResponse(
                    Action.REQLLM, "Rất tiếc, tin tức này không có liên kết khả dụng để lấy nội dung chi tiết.", None
                )

            logger.bind(tag=TAG).debug(
                f"获取新闻详情: {title}, 来源: {source_name}, URL={url}"
            )

            # 获取新闻详情
            detail_content = fetch_news_detail(url)

            if not detail_content or detail_content == "无法获取详细内容":
                return ActionResponse(
                    Action.REQLLM,
                    f"Rất tiếc, không thể lấy nội dung chi tiết của 《{title}》, có thể liên kết đã hết hạn hoặc cấu trúc trang web đã thay đổi.",
                    None,
                )

            # 构建详情报告
            detail_report = (
                f"Dựa trên dữ liệu sau, dùng ngôn ngữ {lang} để trả lời yêu cầu truy vấn chi tiết tin tức của người dùng：\n\n"
                f"Tiêu đề tin tức: {title}\n"
                # f"Nguồn tin tức: {source_name}\n"
                f"Nội dung chi tiết: {detail_content}\n\n"
                f"(Vui lòng tóm tắt nội dung tin tức trên, trích xuất các thông tin chính, thông báo cho người dùng một cách tự nhiên và trôi chảy, "
                f"đừng đề cập rằng đây là bản tóm tắt, hãy giống như đang kể một câu chuyện tin tức hoàn chỉnh)"
            )

            return ActionResponse(Action.REQLLM, detail_report, None)

        # 否则，获取新闻列表并随机选择一条
        # 将中文名称转换为英文ID
        english_source_id = None

        # 检查输入的中文名称是否在配置的新闻源中
        news_sources_list = [
            name.strip() for name in news_sources.split(";") if name.strip()
        ]
        if source in news_sources_list:
            # 如果输入的中文名称在配置的新闻源中，在 CHANNEL_MAP 中查找对应的英文ID
            english_source_id = CHANNEL_MAP.get(source)

        # 如果找不到对应的英文ID，使用默认源
        if not english_source_id:
            logger.bind(tag=TAG).warning(f"无效的新闻源: {source}，使用默认源澎湃新闻")
            english_source_id = "thepaper"
            source = "澎湃新闻"

        logger.bind(tag=TAG).info(f"获取新闻: 新闻源={source}({english_source_id})")

        # 获取新闻列表
        news_items = fetch_news_from_api(conn, english_source_id)

        if not news_items:
            return ActionResponse(
                Action.REQLLM,
                f"Rất tiếc, không thể lấy thông tin tin tức từ {source}, vui lòng thử lại sau hoặc thử nguồn tin tức khác.",
                None,
            )

        # 随机选择一条新闻
        selected_news = random.choice(news_items)

        # 保存当前新闻链接到连接对象，以便后续查询详情
        if not hasattr(conn, "last_newsnow_link"):
            conn.last_newsnow_link = {}
        conn.last_newsnow_link = {
            "url": selected_news.get("url", "#"),
            "title": selected_news.get("title", "未知标题"),
            "source_id": english_source_id,
        }

        # 构建新闻报告
        news_report = (
            f"Dựa trên dữ liệu sau, dùng ngôn ngữ {lang} để trả lời yêu cầu truy vấn tin tức của người dùng：\n\n"
            f"Tiêu đề tin tức: {selected_news['title']}\n"
            # f"Nguồn tin tức: {source}\n"
            f"(Vui lòng thông báo tiêu đề tin tức này cho người dùng một cách tự nhiên và trôi chảy, "
            f"nhắc nhở người dùng có thể yêu cầu lấy nội dung chi tiết để biết thêm thông tin.)"
        )

        return ActionResponse(Action.REQLLM, news_report, None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"获取新闻出错: {e}")
        return ActionResponse(
            Action.REQLLM, "Rất tiếc, đã xảy ra lỗi khi lấy tin tức, vui lòng thử lại sau.", None
        )
