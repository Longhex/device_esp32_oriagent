import unittest
from core.utils.tts import MarkdownCleaner

class TestMarkdownCleaner(unittest.TestCase):
    def test_cases(self):
        cases = [
            {
                "name": "markdown_image_full",
                "input": "Hình ảnh đây: ![Sữa rửa mặt trà xanh](https://content.pancake.vn/a.jpg) Anh có muốn đặt hàng không ạ?",
                "must_not_contain": ["http", "https", "://", "![", "]("],
                "should_contain": ["Sữa rửa mặt trà xanh", "Anh có muốn đặt hàng không"]
            },
            {
                "name": "markdown_link_full",
                "input": "Repo đây: [Headroom](https://github.com/chopratejas/headroom).",
                "must_not_contain": ["http", "https", "://", "]("],
                "should_contain": ["Headroom"]
            },
            {
                "name": "markdown_image_split_missing_bang",
                "input": "[Sữa rửa mặt trà xanh](https://content.pancake.vn/a.jpg) Anh có muốn đặt hàng không ạ?",
                "must_not_contain": ["http", "https", "://", "]("],
                "should_contain": ["Sữa rửa mặt trà xanh", "Anh có muốn đặt hàng không"]
            },
            {
                "name": "broken_markdown_tail",
                "input": "Sữa rửa mặt trà xanh](https://content.pancake.vn/a.jpg) Anh có muốn đặt hàng không ạ?",
                "must_not_contain": ["http", "https", "://", "]("],
                "should_contain": ["Sữa rửa mặt trà xanh", "Anh có muốn đặt hàng không"]
            },
            {
                "name": "raw_url",
                "input": "Anh xem tại https://content.pancake.vn/a.jpg nhé.",
                "must_not_contain": ["http", "https", "://"],
                "should_contain": ["Anh xem"]
            },
            {
                "name": "url_with_query_string",
                "input": "Sản phẩm: https://shop.example.com/product?id=123&color=red&size=L",
                "must_not_contain": ["http", "https", "://", "shop.example.com"],
                "should_contain": ["Sản phẩm"]
            },
            {
                "name": "multiple_images",
                "input": "Ảnh trước: ![A](https://a.jpg) và ảnh sau: ![B](https://b.jpg)",
                "must_not_contain": ["http", "https", "://", "![", "]("],
                "should_contain": ["A", "B"]
            },
            {
                "name": "url_with_parentheses",
                "input": "Wiki: https://en.wikipedia.org/wiki/Python_(programming_language)",
                "must_not_contain": ["http", "https", "://", "wikipedia.org", "programming_language"],
                "should_contain": ["Wiki"]
            },
            {
                "name": "url_inside_code_block",
                "input": "Code mẫu: ```python\nurl='https://example.com/a.jpg'\n``` xong rồi.",
                "must_not_contain": ["http", "https", "://", "example.com"],
                "should_contain": ["Code mẫu", "xong rồi"]
            },
            {
                "name": "normal_parentheses_should_keep",
                "input": "Combo hôm nay gồm sữa rửa mặt (150ml) và toner (100ml).",
                "must_not_contain": ["http", "https", "://"],
                "should_contain": ["150ml", "100ml", "sữa rửa mặt", "toner"]
            },
            {
                "name": "normal_square_brackets_should_keep_content",
                "input": "Sản phẩm [bản mới] đang được giảm giá hôm nay.",
                "must_not_contain": ["http", "https", "://"],
                "should_contain": ["bản mới", "giảm giá"]
            },
            {
                "name": "real_pancake_image_case",
                "input": "Hình ảnh có em nó đây: ![Sữa rửa mặt trà xanh](https://content.pancake.vn/2-25/2025/4/4/642366eba3f6626b670d9cb0c2e5aab9337304e9.jpg)\n\nAnh có muốn đặt hàng không ạ?",
                "must_not_contain": [
                    "http",
                    "https",
                    "://",
                    "content.pancake.vn",
                    "![",
                    "]("
                ],
                "should_contain": [
                    "Sữa rửa mặt trà xanh",
                    "Anh có muốn đặt hàng không"
                ]
            },
            {
                "name": "real_pancake_split_case",
                "input": "[Sữa rửa mặt trà xanh](https://content.pancake.vn/2-25/2025/4/4/642366eba3f6626b670d9cb0c2e5aab9337304e9.jpg)\n\nAnh có muốn đặt hàng không ạ?",
                "must_not_contain": [
                    "http",
                    "https",
                    "://",
                    "content.pancake.vn",
                    "]("
                ],
                "should_contain": [
                    "Sữa rửa mặt trà xanh",
                    "Anh có muốn đặt hàng không"
                ]
            }
        ]
        
        for case in cases:
            with self.subTest(case=case["name"]):
                cleaned = MarkdownCleaner.clean_markdown(case["input"])
                for mnc in case["must_not_contain"]:
                    self.assertNotIn(mnc, cleaned, f"'{mnc}' found in cleaned text: {cleaned}")
                for sc in case["should_contain"]:
                    self.assertIn(sc, cleaned, f"'{sc}' not found in cleaned text: {cleaned}")

if __name__ == '__main__':
    unittest.main()
