import unittest
from core.utils.image_extractor import StreamingImageExtractor


def run_stream(chunks):
    """Cho chuỗi chunk qua extractor, trả (text_ghép, danh_sách_ảnh)."""
    ex = StreamingImageExtractor()
    out, images = [], []
    for c in chunks:
        t, imgs = ex.feed(c)
        out.append(t)
        images.extend(imgs)
    t, imgs = ex.flush()
    out.append(t)
    images.extend(imgs)
    return "".join(out), images


class TestStreamingImageExtractor(unittest.TestCase):
    def test_form_nguyen_ven_mot_chunk(self):
        text, images = run_stream(
            ["Đây là ảnh ![áo thun](https://cdn.x.com/a.jpg) giá 250k."]
        )
        self.assertEqual(images, [("áo thun", "https://cdn.x.com/a.jpg")])
        self.assertNotIn("![", text)
        self.assertNotIn("https://", text)
        self.assertIn("Đây là ảnh", text)
        self.assertIn("giá 250k", text)

    def test_form_bi_cat_qua_nhieu_chunk(self):
        # LLM stream cắt token giữa form ảnh — trường hợp thực tế phổ biến nhất
        text, images = run_stream(
            ["Xem này: ![á", "o](https://cdn.x", ".com/b.png) đẹp không?"]
        )
        self.assertEqual(images, [("áo", "https://cdn.x.com/b.png")])
        self.assertNotIn("![", text)
        self.assertNotIn("https://", text)
        self.assertIn("Xem này:", text)
        self.assertIn("đẹp không?", text)

    def test_khong_co_anh_giu_nguyen_text(self):
        chunks = ["Xin chào! ", "Hôm nay trời đẹp. ", "Bạn khỏe không?"]
        text, images = run_stream(chunks)
        self.assertEqual(images, [])
        self.assertEqual(text, "".join(chunks))

    def test_dau_cham_than_cuoi_chunk_khong_mat(self):
        # "!" cuối chunk bị giữ tạm (nghi là "![" đang gõ dở) nhưng không được mất
        text, images = run_stream(["Tuyệt vời!", " Cảm ơn bạn."])
        self.assertEqual(images, [])
        self.assertEqual(text, "Tuyệt vời! Cảm ơn bạn.")

    def test_form_do_dang_het_stream_thi_nha_ra(self):
        # Stream kết thúc khi form chưa hoàn chỉnh -> flush trả lại nguyên văn
        text, images = run_stream(["Ảnh đây ![áo](https://cdn.x.com/c"])
        self.assertEqual(images, [])
        self.assertIn("![áo](https://cdn.x.com/c", text)

    def test_url_trung_lap_chi_bao_mot_lan(self):
        text, images = run_stream(
            [
                "![a](https://cdn.x.com/same.jpg) và ",
                "![b](https://cdn.x.com/same.jpg) nữa.",
            ]
        )
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0][1], "https://cdn.x.com/same.jpg")

    def test_nhieu_anh_khac_nhau(self):
        text, images = run_stream(
            ["![a](https://x.com/1.jpg) rồi ![b](https://x.com/2.jpg) xong."]
        )
        self.assertEqual(
            [u for _, u in images],
            ["https://x.com/1.jpg", "https://x.com/2.jpg"],
        )
        self.assertEqual(text.replace("  ", " ").strip(), "rồi xong.")

    def test_khong_nhan_scheme_khac_http(self):
        # javascript:/data: không khớp regex -> để nguyên (MarkdownCleaner phía sau dọn)
        text, images = run_stream(["![x](javascript:alert(1)) hết."])
        self.assertEqual(images, [])

    def test_link_thuong_khong_phai_anh_thi_bo_qua(self):
        # [text](url) không có "!" -> không phải ảnh, extractor không đụng vào
        text, images = run_stream(["Xem [tài liệu](https://x.com/doc) nhé."])
        self.assertEqual(images, [])
        self.assertIn("[tài liệu](https://x.com/doc)", text)


if __name__ == "__main__":
    unittest.main()
