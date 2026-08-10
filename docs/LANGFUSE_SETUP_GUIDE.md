# Hướng Dẫn Tích Hợp Langfuse (Trực Tiếp Vào Docker Compose Dự Án)

Tài liệu này hướng dẫn chi tiết cách tích hợp **Langfuse** trực tiếp vào `docker-compose.yml` của dự án **TravelPlanner**. 

Mục tiêu: Khi bạn hoặc bất kỳ thành viên nào trong team gõ **`docker compose up`**, toàn bộ ứng dụng (Backend, Postgres, Valhalla, OpenTripPlanner và **Langfuse**) sẽ đồng loạt khởi động và kết nối sẵn sàng với nhau!

---

## 🏗️ 1. Mô Hình Kết Nối Trong Docker Network

```text
 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │                            Docker Network (travelplanner_default)               │
 │                                                                                 │
 │  ┌────────────────┐     http://langfuse:3000     ┌───────────────────────────┐  │
 │  │    backend     ├─────────────────────────►│         langfuse          │  │
 │  └───────┬────────┘                          │  (Web UI: localhost:3005) │  │
 │          │                                   └─────────────┬─────────────┘  │
 │          │ DB                                              │ DB             │
 │  ┌───────▼────────┐                          ┌─────────────▼─────────────┐  │
 │  │    postgres    │                          │        langfuse-db        │  │
 │  └────────────────┘                          └───────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────────────────┘
```

### Ưu điểm nổi bật:
1. **Một lệnh duy nhất:** Chỉ cần `docker compose up --build` là có trọn bộ ứng dụng + Langfuse Log.
2. **Giao tiếp nội bộ siêu nhanh:** Backend gọi Langfuse trực tiếp qua tên container `http://langfuse:3000` mà không cần cấu hình IP rắc rối.
3. **Đồng bộ cả team:** Bạn bè pull code về gõ 1 lệnh là có môi trường phát triển & trace log giống hệt nhau.

---

## 🚀 2. Cấu Hình Service Trong `docker-compose.yml`

Bổ sung 2 dịch vụ `langfuse-db` và `langfuse` vào file `docker-compose.yml` của dự án:

```yaml
services:
  # ... các services hiện tại (postgres, backend, valhalla...) ...

  langfuse-db:
    image: postgres:16-alpine
    container_name: travelplanner-langfuse-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse_password
      POSTGRES_DB: langfuse
    ports:
      - "5433:5432"
    volumes:
      - langfuse_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse -d langfuse"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse:
    image: langfuse/langfuse:2.95.11
    container_name: travelplanner-langfuse
    restart: unless-stopped
    depends_on:
      langfuse-db:
        condition: service_healthy
    ports:
      - "3005:3000"
    environment:
      NODE_ENV: production
      DATABASE_URL: postgresql://langfuse:langfuse_password@langfuse-db:5432/langfuse
      NEXTAUTH_URL: http://localhost:3005
      NEXTAUTH_SECRET: travelplanner_langfuse_secret_key_2026
      SALT: travelplanner_langfuse_salt_2026
      TELEMETRY_ENABLED: "false"

volumes:
  # ... volumes hiện tại ...
  langfuse_postgres_data:
```

---

## 💻 3. Cấu Hình Biến Môi Trường Cho Backend

Trong section `environment:` của dịch vụ `backend` trong `docker-compose.yml` (hoặc file `backend/.env`), thêm các dòng cấu hình:

```yaml
  backend:
    # ...
    environment:
      # ...
      LANGFUSE_ENABLED: "true"
      LANGFUSE_PUBLIC_KEY: "${LANGFUSE_PUBLIC_KEY:-}"
      LANGFUSE_SECRET_KEY: "${LANGFUSE_SECRET_KEY:-}"
      LANGFUSE_HOST: "http://langfuse:3000"  # Kết nối nội bộ qua tên container trong Docker
```

---

## 🗝️ 4. Quy Trình Sử Dụng 3 Bước Cho Cả Team

### Bước 1: Khởi động toàn bộ hệ thống
Bất kỳ ai trong team chỉ cần chạy:
```bash
docker compose up -d --build
```

### Bước 2: Tạo API Keys trên Langfuse UI (Lần đầu tiên)
1. Mở trình duyệt truy cập: **`http://localhost:3005`**
2. Đăng ký tài khoản Admin local $\rightarrow$ Bấm **Create Project** tên **`TravelPlanner`**.
3. Vào **Settings** $\rightarrow$ **API Keys** $\rightarrow$ Bấm **Create new API keys**.
4. Sao chép cặp **Public Key** (`pk-lf-...`) và **Secret Key** (`sk-lf-...`) dán vào file `backend/.env` cá nhân.

### Bước 3: Thử nghiệm & Xem Log
* Vào giao diện Web thực hiện chat / tạo hành trình du lịch.
* Mở **`http://localhost:3005/project/TravelPlanner/traces`** để xem ngay cây log AI hiển thị trực quan!

Generation mới sẽ có provider, model, input/output/total token và thống kê đầu
vào/đầu ra an toàn (độ dài, loại tác vụ, số ảnh). Backend không gửi raw prompt,
payload người dùng, byte ảnh hoặc toàn bộ model output sang Langfuse. Các trace
đã tạo trước khi cập nhật instrumentation sẽ không được backfill token.

Các provider call trong runtime đều được trace, gồm LLM Planner/Profile,
structured/grounded JSON, image input, URL-reel audio STT, frame vision, caption
structuring và source-observation fusion. Các script maintenance chạy độc lập
ngoài FastAPI không tự bật tracing.

Nếu token đã có nhưng cost vẫn là `$0.00`, model hiện tại chưa khớp model-price
definition của Langfuse v2. Tạo custom model definition trong
**Project Settings → Models** với đúng model name hiển thị trên generation; không
hard-code bảng giá vào backend vì giá provider thay đổi theo thời gian.

Sau khi đổi key hoặc cấu hình Langfuse, recreate backend để tiến trình nhận biến
môi trường mới:

```bash
docker compose up -d --build --force-recreate backend
```

Nếu trace mới vẫn không xuất hiện, xác nhận backend đã nhận cấu hình mà không in
giá trị secret:

```bash
docker compose exec backend python -c "from app.core.config import settings; print(settings.langfuse_enabled, bool(settings.langfuse_public_key), bool(settings.langfuse_secret_key), settings.langfuse_host)"
```
