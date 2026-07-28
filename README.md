# VSF Travel Planner

VSF Travel Planner là nền tảng lập kế hoạch du lịch có AI hỗ trợ, kết hợp với
chợ lịch trình dành cho người đi du lịch và nhà sáng tạo nội dung. Người dùng có
thể tự tạo hoặc mua lịch trình, cá nhân hóa, sử dụng trong chuyến đi và đánh giá
sau khi hoàn thành. Nhà sáng tạo có thể chuyển kinh nghiệm du lịch thực tế thành
các lịch trình có thể chỉnh sửa và bán trên Marketplace.

Luận điểm cốt lõi của sản phẩm là: chỉ tạo ra một lịch trình là chưa đủ. Một kế
hoạch du lịch hữu ích phải có khả năng so sánh, chỉnh sửa, hiển thị lộ trình,
đáng tin cậy, hỗ trợ cộng tác và đồng hành cùng người dùng trong suốt chuyến đi.

## Trạng thái hiện tại

Repository này đang ở giai đoạn khởi tạo kỹ thuật, chưa phải một MVP hoàn chỉnh.

- Frontend Next.js hiện minh họa chức năng tạo và xem danh sách người dùng.
- Backend FastAPI đã có chức năng tạo/đọc người dùng và lưu bằng SQLAlchemy.
- Module lập kế hoạch đã có ranh giới cho các bước Explorer, Planner, Finder,
  Check và Backup, nhưng vẫn dùng LLM giả lập và lưu plan trong bộ nhớ.
- Profile Planner và danh mục Marketplace mới chỉ là các endpoint minh họa.
- Xác thực, bản đồ, nhập dữ liệu từ URL, chỉnh sửa plan, chế độ offline,
  giao dịch Marketplace, thanh toán, đánh giá và phân tích cho creator chưa được
  triển khai.

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

## Tài liệu dự án

Hãy bắt đầu với [AGENTS.md](AGENTS.md), sau đó đọc các tài liệu liên quan đến
công việc cần thực hiện. Tài liệu luôn phân biệt rõ sản phẩm mục tiêu và hành vi
đã tồn tại trong code. Khi code và tài liệu không thống nhất, cần kiểm tra code
và cập nhật tài liệu liên quan trong cùng một thay đổi.
