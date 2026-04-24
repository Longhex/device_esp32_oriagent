import requests
from bs4 import BeautifulSoup
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.util import get_ip_info
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Lấy thông tin thời tiết của một địa điểm nhất định. Người dùng nên cung cấp vị trí, ví dụ: 'thời tiết Hà Nội', tham số là: 'Hà Nội'."
            "Nếu người dùng nói tên tỉnh, mặc định lấy thành phố tỉnh lỵ. Nếu người dùng nói địa danh không phải tỉnh/thành phố, mặc định lấy tỉnh lỵ của tỉnh đó."
            "Nếu người dùng không chỉ định địa điểm, ví dụ 'thời tiết thế nào', 'hôm nay thời tiết sao', tham số location để trống."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Tên địa điểm, ví dụ: Hà Nội. Tham số tùy chọn, không bắt buộc.",
                },
                "lang": {
                    "type": "string",
                    "description": "Mã ngôn ngữ người dùng, ví dụ: zh_CN/vi_VN/en_US. Mặc định vi_VN",
                },
            },
            "required": ["lang"],
        },
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    )
}

# Weather code https://dev.qweather.com/docs/resource/icons/#weather-icons
WEATHER_CODE_MAP = {
    "100": "Trời nắng",
    "101": "Nhiều mây",
    "102": "Ít mây",
    "103": "Nắng xen kẽ mây",
    "104": "Âm u",
    "150": "Trời nắng",
    "151": "Nhiều mây",
    "152": "Ít mây",
    "153": "Nắng xen kẽ mây",
    "300": "Mưa rào",
    "301": "Mưa rào mạnh",
    "302": "Mưa dông",
    "303": "Mưa dông mạnh",
    "304": "Mưa dông kèm mưa đá",
    "305": "Mưa nhỏ",
    "306": "Mưa vừa",
    "307": "Mưa to",
    "308": "Mưa cực lớn",
    "309": "Mưa phùn/Mưa rây",
    "310": "Mưa bão",
    "311": "Mưa bão lớn",
    "312": "Mưa bão cực lớn",
    "313": "Mưa đóng băng",
    "314": "Mưa nhỏ đến vừa",
    "315": "Mưa vừa đến to",
    "316": "Mưa to đến bão",
    "317": "Mưa bão đến bão lớn",
    "318": "Mưa bão lớn đến cực lớn",
    "350": "Mưa rào",
    "351": "Mưa rào mạnh",
    "399": "Mưa",
    "400": "Tuyết rơi nhỏ",
    "401": "Tuyết rơi vừa",
    "402": "Tuyết rơi dày",
    "403": "Bão tuyết",
    "404": "Mưa tuyết",
    "405": "Thời tiết mưa tuyết",
    "406": "Mưa rào tuyết",
    "407": "Tuyết rơi từng đợt",
    "408": "Tuyết nhỏ đến vừa",
    "409": "Tuyết vừa đến dày",
    "410": "Tuyết dày đến bão tuyết",
    "456": "Mưa rào tuyết",
    "457": "Tuyết rơi từng đợt",
    "499": "Tuyết",
    "500": "Sương mù mỏng",
    "501": "Sương mù",
    "502": "Khói bụi",
    "503": "Cát bay",
    "504": "Bụi lơ lửng",
    "507": "Bão cát",
    "508": "Bão cát mạnh",
    "509": "Sương mù dày đặc",
    "510": "Sương mù rất dày",
    "511": "Khói bụi vừa",
    "512": "Khói bụi nặng",
    "513": "Khói bụi nghiêm trọng",
    "514": "Sương mù lớn",
    "515": "Sương mù cực dày",
    "900": "Nóng",
    "901": "Lạnh",
    "999": "Không rõ",
}


def fetch_city_info(location, api_key, api_host):
    url = f"https://{api_host}/geo/v2/city/lookup?key={api_key}&location={location}&lang=zh"
    response = requests.get(url, headers=HEADERS).json()
    if response.get("error") is not None:
        logger.bind(tag=TAG).error(
            f"Failed to fetch weather, reason: {response.get('error', {}).get('detail')}"
        )
        return None
    return response.get("location", [])[0] if response.get("location") else None


def fetch_weather_page(url):
    response = requests.get(url, headers=HEADERS)
    return BeautifulSoup(response.text, "html.parser") if response.ok else None


def parse_weather_info(soup):
    city_name = soup.select_one("h1.c-submenu__location").get_text(strip=True)

    current_abstract = soup.select_one(".c-city-weather-current .current-abstract")
    current_abstract = (
        current_abstract.get_text(strip=True) if current_abstract else "Không rõ"
    )

    current_basic = {}
    for item in soup.select(
        ".c-city-weather-current .current-basic .current-basic___item"
    ):
        parts = item.get_text(strip=True, separator=" ").split(" ")
        if len(parts) == 2:
            key, value = parts[1], parts[0]
            current_basic[key] = value

    temps_list = []
    for row in soup.select(".city-forecast-tabs__row")[:7]:  # 取前7天的数据
        date = row.select_one(".date-bg .date").get_text(strip=True)
        weather_code = (
            row.select_one(".date-bg .icon")["src"].split("/")[-1].split(".")[0]
        )
        weather = WEATHER_CODE_MAP.get(weather_code, "Không rõ")
        temps = [span.get_text(strip=True) for span in row.select(".tmp-cont .temp")]
        high_temp, low_temp = (temps[0], temps[-1]) if len(temps) >= 2 else (None, None)
        temps_list.append((date, weather, high_temp, low_temp))

    return city_name, current_abstract, current_basic, temps_list


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def get_weather(conn: "ConnectionHandler", location: str = None, lang: str = "vi_VN"):
    from core.utils.cache.manager import cache_manager, CacheType

    weather_config = conn.config.get("plugins", {}).get("get_weather", {})
    api_host = weather_config.get("api_host", "mj7p3y7naa.re.qweatherapi.com")
    api_key = weather_config.get("api_key", "a861d0d5e7bf4ee1a83d9a9e4f96d4da")
    default_location = weather_config.get("default_location", "Hồ Chí Minh")
    client_ip = conn.client_ip

    # 优先使用用户提供的location参数
    if not location:
        # 通过客户端IP解析城市
        if client_ip:
            # 先从缓存获取IP对应的城市信息
            cached_ip_info = cache_manager.get(CacheType.IP_INFO, client_ip)
            if cached_ip_info:
                location = cached_ip_info.get("city")
            else:
                # 缓存未命中，调用API获取
                ip_info = get_ip_info(client_ip, logger)
                if ip_info:
                    cache_manager.set(CacheType.IP_INFO, client_ip, ip_info)
                    location = ip_info.get("city")

            if not location:
                location = default_location
        else:
            # 若无IP，使用默认位置
            location = default_location
    # 尝试从缓存获取完整天气报告
    weather_cache_key = f"full_weather_{location}_{lang}"
    cached_weather_report = cache_manager.get(CacheType.WEATHER, weather_cache_key)
    if cached_weather_report:
        return ActionResponse(Action.REQLLM, cached_weather_report, None)

    # 缓存未命中，获取实时天气数据
    city_info = fetch_city_info(location, api_key, api_host)
    if not city_info:
        return ActionResponse(
            Action.REQLLM, f"Không tìm thấy thành phố liên quan: {location}, vui lòng xác nhận lại địa điểm", None
        )
    soup = fetch_weather_page(city_info["fxLink"])
    if not soup:
        return ActionResponse(Action.REQLLM, None, "Yêu cầu thất bại")
    city_name, current_abstract, current_basic, temps_list = parse_weather_info(soup)

    weather_report = f"Vị trí bạn truy vấn là：{city_name}\n\nThời tiết hiện tại: {current_abstract}\n"

    # 添加有效的当前天气参数
    if current_basic:
        weather_report += "Thông số chi tiết：\n"
        for key, value in current_basic.items():
            if value != "0":  # 过滤无效值
                weather_report += f"  · {key}: {value}\n"

    # 添加7天预报
    weather_report += "\nDự báo 7 ngày tới：\n"
    for date, weather, high, low in temps_list:
        weather_report += f"{date}: {weather}, nhiệt độ {low}~{high}\n"

    # 提示语
    weather_report += "\n(Nếu cần thời tiết cụ thể của một ngày nào đó, vui lòng cho tôi biết ngày cụ thể)"

    # 缓存完整的天气报告
    cache_manager.set(CacheType.WEATHER, weather_cache_key, weather_report)

    return ActionResponse(Action.REQLLM, weather_report, None)
