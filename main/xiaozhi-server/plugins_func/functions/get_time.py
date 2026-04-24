from datetime import datetime
import cnlunar
from plugins_func.register import register_function, ToolType, ActionResponse, Action

get_lunar_function_desc = {
    "type": "function",
    "function": {
        "name": "get_lunar",
        "description": (
            "Dùng để lấy thông tin âm lịch và hoàng đạo cho một ngày cụ thể."
            "Người dùng có thể chỉ định nội dung truy vấn, như: ngày âm lịch, thiên can địa chi, tiết khí, con giáp, cung hoàng đạo, bát tự, giờ hoàng đạo, v.v."
            "Nếu không chỉ định nội dung truy vấn, mặc định sẽ truy vấn can chi năm và ngày âm lịch."
            "Đối với các câu hỏi cơ bản như 'hôm nay là ngày bao nhiêu âm', 'ngày âm hôm nay', vui lòng sử dụng thông tin trong ngữ cảnh, đừng gọi công cụ này."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Ngày cần truy vấn, định dạng YYYY-MM-DD, ví dụ: 2024-01-01. Nếu không cung cấp, mặc định dùng ngày hiện tại",
                },
                "query": {
                    "type": "string",
                    "description": "Nội dung cần truy vấn, ví dụ: ngày âm lịch, thiên can địa chi, ngày lễ, tiết khí, con giáp, cung hoàng đạo, bát tự, v.v.",
                },
            },
            "required": [],
        },
    },
}


@register_function("get_lunar", get_lunar_function_desc, ToolType.WAIT)
def get_lunar(date=None, query=None):
    """
    用于获取当前的阴历/农历，和天干地支、节气、生肖、星座、八字、宜忌等黄历信息
    """
    from core.utils.cache.manager import cache_manager, CacheType

    # 如果提供了日期参数，则使用指定日期；否则使用当前日期
    if date:
        try:
            now = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return ActionResponse(
                Action.REQLLM,
                f"Định dạng ngày sai, vui lòng sử dụng YYYY-MM-DD, ví dụ: 2024-01-01",
                None,
            )
    else:
        now = datetime.now()

    current_date = now.strftime("%Y-%m-%d")

    # 如果 query 为 None，则使用默认文本
    if query is None:
        query = "Truy vấn can chi năm và ngày âm lịch mặc định"

    # Thử lấy thông tin âm lịch từ bộ nhớ đệm
    lunar_cache_key = f"lunar_info_{current_date}"
    cached_lunar_info = cache_manager.get(CacheType.LUNAR, lunar_cache_key)
    if cached_lunar_info:
        return ActionResponse(Action.REQLLM, cached_lunar_info, None)

    response_text = f"Dựa trên thông tin sau để trả lời yêu cầu của người dùng, và cung cấp thông tin liên quan đến {query}：\n"

    lunar = cnlunar.Lunar(now, godType="8char")
    response_text += (
        "Thông tin âm lịch：\n"
        "Năm %s Tháng %s Ngày %s\n" % (lunar.lunarYearCn, lunar.lunarMonthCn[:-1], lunar.lunarDayCn)
        + "Can chi: Năm %s Tháng %s Ngày %s\n" % (lunar.year8Char, lunar.month8Char, lunar.day8Char)
        + "Con giáp: Tuổi %s\n" % (lunar.chineseYearZodiac)
        + "Bát tự: %s\n"
        % (
            " ".join(
                [lunar.year8Char, lunar.month8Char, lunar.day8Char, lunar.twohour8Char]
            )
        )
        + "Lễ hội hôm nay: %s\n"
        % (
            ",".join(
                filter(
                    None,
                    (
                        lunar.get_legalHolidays(),
                        lunar.get_otherHolidays(),
                        lunar.get_otherLunarHolidays(),
                    ),
                )
            )
        )
        + "Tiết khí hôm nay: %s\n" % (lunar.todaySolarTerms)
        + "Tiết khí tiếp theo: %s Năm %s Tháng %s Ngày %s\n"
        % (
            lunar.nextSolarTerm,
            lunar.nextSolarTermYear,
            lunar.nextSolarTermDate[0],
            lunar.nextSolarTermDate[1],
        )
        + "Bảng tiết khí năm nay: %s\n"
        % (
            ", ".join(
                [
                    f"{term}(Tháng {date[0]} Ngày {date[1]})"
                    for term, date in lunar.thisYearSolarTermsDic.items()
                ]
            )
        )
        + "Xung sát: %s\n" % (lunar.chineseZodiacClash)
        + "Cung hoàng đạo: %s\n" % (lunar.starZodiac)
        + "Nạp âm: %s\n" % lunar.get_nayin()
        + "Bách kỵ: %s\n" % (lunar.get_pengTaboo(delimit=", "))
        + "Trực: Trực %s\n" % lunar.get_today12DayOfficer()[0]
        + "Thần: %s(%s)\n"
        % (lunar.get_today12DayOfficer()[1], lunar.get_today12DayOfficer()[2])
        + "Nhị thập bát tú: %s\n" % lunar.get_the28Stars()
        + "Hướng cát thần: %s\n" % " ".join(lunar.get_luckyGodsDirection())
        + "Thai thần hôm nay: %s\n" % lunar.get_fetalGod()
        + "Nên làm: %s\n" % "、".join(lunar.goodThing[:10])
        + "Kiêng kỵ: %s\n" % "、".join(lunar.badThing[:10])
        + "(Mặc định trả về năm can chi và ngày âm lịch; chỉ khi yêu cầu thông tin nên làm/kiêng kỵ mới trả về chi tiết này)"
    )

    # 缓存农历信息
    cache_manager.set(CacheType.LUNAR, lunar_cache_key, response_text)

    return ActionResponse(Action.REQLLM, response_text, None)
