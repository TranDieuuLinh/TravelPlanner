# VSF Travel Planner

VSF Travel Planner biến nguồn cảm hứng du lịch thành lịch trình có thể sử dụng
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
VSF_TravelPlanner/
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
│   ├── 12-roadmap-person-c.md
│   ├── assets/
│   ├── glossary.md
│   └── decisions/
├── frontend/
├── backend/
└── docker-compose.yml
```

## Chạy dự án trên máy cá nhân

Khởi động PostgreSQL:

```bash
docker compose up postgres
```

Khởi động backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./scripts/migrate.sh
uvicorn app.main:app --reload
```

Tài liệu API có tại `http://localhost:8000/docs`.

Khởi động frontend:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend có tại `http://localhost:3000`.

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
