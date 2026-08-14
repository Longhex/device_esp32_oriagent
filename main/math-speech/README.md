# Math speech sidecar

Service này chuyển LaTeX sang MathML bằng `latex2mathml`. Sau đó
`vietnamese_renderer.py` đọc cây MathML theo cấu trúc để bảo toàn phạm vi
phân số, căn, số mũ, ngoặc, hàm và các toán tử lớn. Nếu gặp phần
tử hoặc ký hiệu chưa có trong renderer, service tự động giao toàn bộ
công thức cho MathCAT/MathCATForPython. Nhờ đó cách đọc cốt lõi ổn định
mà không làm hẹp độ phủ công thức.

Server TTS chính chỉ gọi HTTP nội bộ, nên vẫn giữ Python 3.10 và không
phải nạp Rust extension.

Chuẩn bị artifact một lần:

```bash
chmod +x scripts/*.sh
./scripts/bootstrap_vendor.sh
```

Chạy độc lập:

```bash
docker build -t oriagent-math-speech:local .
docker run --rm -p 127.0.0.1:18100:8100 oriagent-math-speech:local
curl http://127.0.0.1:18100/health
curl -H 'content-type: application/json' \
  -d '{"latex":"\\frac{1}{2}"}' http://127.0.0.1:18100/speak
```

## Cách đọc phân số

Quy ước đang dùng:

| Trường hợp | Đọc | Ví dụ |
|---|---|---|
| Tử và mẫu đều là **giá trị cụ thể** | `phần` | `1/2` → "một phần hai", `25/7` → "hai mươi lăm phần bảy" |
| Có **ẩn / tên biến** | `trên` | `a/b` → "a trên b", `a/2` → "a trên hai" |
| Tử hoặc mẫu là **biểu thức ghép** | `phân số … tất cả trên …` | `(a+1)/2` → "phân số, a cộng một, tất cả trên hai" |
| **Đơn vị** | `trên` (không đổi) | `m/s` → "mét trên giây" |
| Dấu `÷` | `chia` (không đổi) | `a ÷ b` → "a chia b" |

Vế thứ ba tồn tại để `(a+1)/2` nghe khác hẳn `a + 1/2` ("a cộng
một phần hai"). Renderer chỉ thêm dấu đóng khi thiếu nó sẽ gây nhập nhằng;
ví dụ `\sqrt{a+b}+c` có "hết căn", còn `\sqrt{a+b+c}` thì không.

Luật nằm ở `SimpleSpeak_Rules.yaml`: `simple` + `default` cho `\frac`, và hai
luật mrow `slash-simple` + `slash-compound` cho dấu `/` viết thẳng (latex2mathml
sinh `<mo>/</mo>` chứ không phải `<mfrac>` nên phải bắt riêng).

## Kiểm thử renderer

```bash
python -m unittest discover -s tests -p "test_vietnamese_renderer.py"
```

Bộ test khóa các cặp dễ nhập nhằng, số thành chữ, hàm, logarit, đạo
hàm, tích phân, giới hạn, tổng, tích, trị tuyệt đối và ma trận.

## Sửa cách đọc tiếng Việt

Bộ luật tiếng Việt của MathCAT v0.7.3 là bản dịch máy nên nhiều chỗ đọc không
đúng chuẩn (`∏` đọc "pi", `log` đọc "lóc", `|x|` đọc "trị tuyệt đối **của của**
x"...). Ta **không** sửa trực tiếp `vendor/Rules` vì phải khớp
sha256 trong `UPSTREAMS.lock` và bị `bootstrap_vendor.sh` ghi đè.

Thay vào đó, các chỉnh sửa nằm trong `rules_overrides/vi.json`, và
`scripts/apply_rule_overrides.py` sinh ra cây luật hiệu lực tại `rules/`
(Dockerfile chạy bước này lúc build; `app.py` tự ưu tiên `rules/` nếu có).

Mỗi mục override khớp **nguyên một dòng** (`find`/`replace`) hoặc **một khối
dòng liền nhau** (`find_block`/`replace_block`, dùng để viết lại hoặc chèn luật
mới), và bắt buộc đúng số lần khai báo ở `count`. Nếu upstream đổi nội dung,
build fail ngay thay vì âm thầm phát sai.

Thêm một sửa đổi mới:

```bash
# xem nội dung luật gốc để lấy đúng dòng cần khớp
unzip -p vendor/Rules/Languages/vi/vi.zip SimpleSpeak_Rules.yaml | less
# thêm mục vào rules_overrides/vi.json rồi kiểm tra
python3 scripts/apply_rule_overrides.py
python3 -m unittest discover -s tests -p "test_rule_overrides.py"
```

`tests/test_rule_overrides.py` chạy được trên Python 3.10 (không cần MathCAT);
`tests/test_app.py` cần môi trường 3.11 trong image.

Sau khi sửa phải build lại image thì thay đổi mới có hiệu lực:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.dev.local-ports.yml \
  up -d --build math-speech
```

MathCAT có trạng thái toàn cục, vì vậy app dùng khóa và chỉ chạy một worker.
Client phía server có timeout và circuit breaker; khi sidecar lỗi, công thức gốc
được giữ lại thay vì làm hỏng toàn bộ lượt nói.
