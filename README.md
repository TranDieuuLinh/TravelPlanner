# TravelPlanner

TravelPlanner biến nguồn cảm hứng du lịch thành lịch trình có thể sử dụng
thực tế. Người dùng có thể dán URL video hoặc nội dung tham khảo, kiểm tra các
địa điểm được hệ thống trích xuất, bổ sung ngày đi, ngân sách và ràng buộc, sau
đó nhận Main Plan đã được kiểm tra cùng Backup Plan riêng khi cần.

Sản phẩm đồng thời có Marketplace để creator chuyển nội dung và kinh nghiệm
thực tế thành plan có version để xuất bản và bán. Buyer nhận một bản sao cá nhân
có thể chỉnh sửa bằng cùng công cụ Planner, không làm thay đổi plan gốc của
creator.

Luận điểm cốt lõi là: giá trị không nằm ở việc sinh ra một đoạn lịch trình bằng
AI, mà ở toàn bộ chuỗi `URL -> ngữ cảnh có nguồn -> địa điểm đã xác nhận ->
plan có cấu trúc -> kiểm tra tính khả thi -> plan có thể chỉnh sửa và sử dụng`.

## Trạng thái hiện tại

Repository này đang ở giai đoạn khởi tạo kỹ thuật, chưa phải một MVP hoàn chỉnh.

- Frontend Next.js đã có đăng ký, đăng nhập bằng cookie, hồ sơ cá nhân và form
  đăng ký creator kết nối backend thật.
- Backend FastAPI đã có authentication, refresh session, CSRF, RBAC, hồ sơ,
  creator application và lưu bằng SQLAlchemy.
- Module lập kế hoạch đã có ranh giới cho các bước Explorer, Planner, Finder,
  Check và Backup, nhưng vẫn dùng LLM giả lập và lưu plan trong bộ nhớ.
- Danh mục Marketplace vẫn chỉ là endpoint minh họa; contract giao tiếp giữa
  Marketplace và Planner đã được định nghĩa nhưng chưa có listing thật.
- Bản đồ, nhập dữ liệu từ URL, chỉnh sửa plan, chế độ offline, listing, giao dịch
  Marketplace, thanh toán, đánh giá và phân tích cho creator chưa được triển
  khai.

Xem [Phạm vi MVP](docs/04-mvp-scope.md) để biết ranh giới phát triển chính thức.

## Cấu trúc kho mã

```text
travelplanner/
├── README.md
├── AGENTS.md
├── docs/
│   ├── 01-product-overview.md
│   ├── 02-user-personas.md
│   ├── 03-user-flows.md
│   ├── 04-mvp-scope.md
│   ├── 05-system-architecture.md
│   ├── 06-domain-model.md
│   ├── 07-api-contracts.md
│   ├── 08-ai-planner-spec.md
│   ├── 09-data-sources.md
│   ├── 10-testing-strategy.md
│   ├── 11-security-and-privacy.md
│   ├── 12-roadmap.md
│   ├── assets/
│   ├── glossary.md
│   └── decisions/
├── frontend/
│   └── src/
│       ├── app/                   # Next.js routes và layout
│       ├── features/              # Module theo domain
│       ├── shared/                # HTTP client/hạ tầng dùng chung
│       └── components/            # App shell và visual dùng chung
├── admin-frontend/               # Console nội bộ quan sát planning runs
├── backend/
└── docker-compose.yml
```

Sơ đồ chi tiết trách nhiệm của từng module nằm trong
[`docs/16-codebase-module-map.md`](docs/16-codebase-module-map.md).

## Chạy dự án trên máy cá nhân

Docker Compose chạy các service backend gồm PostgreSQL, backend, sidecar Google
Maps và hai routing service:

```bash
docker compose up --build
```

API và tài liệu API có tại `http://localhost:8000` và
`http://localhost:8000/docs`. Backend tự chạy Alembic đến revision mới nhất
trước khi nhận request. Dữ liệu PostgreSQL nằm trong volume `postgres_data`.
Image sidecar tự cài package Playwright đã pin, Chromium và các thư viện hệ điều
hành cần thiết khi build; không cần cài Playwright hoặc browser trên máy host.
Frontend người dùng và Planning Control chạy riêng trên host bằng `npm run dev`.
Valhalla chạy tại `http://localhost:8002`.
OpenTripPlanner chạy tại `http://localhost:8080` khi đã chuẩn bị graph và feed
theo `routing-data/README.md`; nếu chưa có dữ liệu, container vẫn được giữ ở
trạng thái chờ và backend dùng fallback route.

Khi cần chạy backend trực tiếp trên host nhưng vẫn dùng PostgreSQL trong Docker:

```bash
docker compose up -d postgres
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./scripts/migrate.sh
uvicorn app.main:app --reload
```

Chạy frontend riêng trên host:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Planning Control là một Next.js app riêng; khi chạy trên host, nó dùng
`http://localhost:3001`:

```bash
cd admin-frontend
npm install
cp .env.example .env.local
npm run dev
```

Trong mục Golden dataset, admin có thể chạy từng case qua module runtime thật
và xem effective input, actual output, duration, lỗi contract cùng mismatch so
với golden projection. Các case dùng URL/LLM có thể gọi provider thật.

## Kiểm thử

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm run typecheck
npm run build
```

## Tài liệu dự án

Hãy bắt đầu với [AGENTS.md](AGENTS.md), sau đó đọc các tài liệu liên quan đến
công việc cần thực hiện. Tài liệu luôn phân biệt rõ sản phẩm mục tiêu và hành vi
đã tồn tại trong code. Khi code và tài liệu không thống nhất, cần kiểm tra code
và cập nhật tài liệu liên quan trong cùng một thay đổi.
