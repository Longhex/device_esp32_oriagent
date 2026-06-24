from core.utils.tts import MarkdownCleaner

cases = [
    "Hình ảnh có em nó đây: ![Sữa rửa mặt trà xanh](https://content.pancake.vn/2-25/2025/4/4/642366eba3f6626b670d9cb0c2e5aab9337304e9.jpg)\n\nAnh có muốn đặt hàng không ạ?",
    "[Sữa rửa mặt trà xanh](https://content.pancake.vn/2-25/2025/4/4/642366eba3f6626b670d9cb0c2e5aab9337304e9.jpg)\n\nAnh có muốn đặt hàng không ạ?",
    "Wiki: https://en.wikipedia.org/wiki/Python_(programming_language)",
    "Combo hôm nay gồm sữa rửa mặt (150ml) và toner (100ml)."
]
for c in cases:
    print(repr(MarkdownCleaner.clean_markdown(c)))
