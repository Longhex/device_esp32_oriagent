# Hướng dẫn chạy dự án Xiaozhi Server (Môi trường Dev Local)


================================================
cd /opt/oriagent/app/deploy
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml build --no-cache   
docker compose -f docker-compose.prod.yml logs -f xiaozhi-server



Đây là cách tốt nhất và nhanh nhất để chạy dự án trên máy Mac của bạn, giúp bạn vừa có thể sửa code giao diện (Frontend) vừa có Backend chạy ổn định trong Docker.

## 1. Yêu cầu hệ thống
*   **Docker Desktop**: Đã cài đặt và đang chạy.
*   **Node.js & npm**: (Để chạy Frontend với chế độ Hot-Reload).

## 2. Khởi động Cơ sở hạ tầng & Backend (Docker)
Thay vì chạy thủ công Java/Maven, chúng ta sẽ chạy toàn bộ MySQL, Redis và Backend API trong Docker.

Mở terminal tại thư mục gốc của dự án và chạy:
```bash
docker compose -f docker-compose.dev.yml up -d --build
```
Lệnh này sẽ:
*   Khởi động MySQL (cổng 3306)
*   Khởi động Redis (cổng 6379)
*   Tự động build và chạy **Backend API** (cổng 8002)

*Kiểm tra trạng thái:* `docker compose -f docker-compose.dev.yml ps` (Tất cả phải là `Up`).

## 3. Chạy Frontend (manager-web) - Có Hot-Reload
Để khi bạn sửa code giao diện, trình duyệt tự động cập nhật ngay lập tức:

Mở một terminal mới:
```bash
cd main/manager-web
npm install   # Nếu là lần đầu chạy
npm run serve
```

## ⚠️ Khắc phục lỗi thường gặp
-   **Lỗi kết nối database:** Kiểm tra xem Docker đã chạy chưa bằng lệnh `docker ps`.
-   **Lỗi NPM:** Nếu gặp lỗi thư viện, hãy xóa thư mục `node_modules` và chạy lại `npm install`.
-   **Cổng (Port) bị chiếm:** Đảm bảo không có dịch vụ nào khác đang chạy trên cổng 3306, 6379, 8001, 8002.


