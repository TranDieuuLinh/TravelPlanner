# Cấu trúc codebase hiện tại

Cập nhật lần cuối: 2026-08-10.

## Các ứng dụng cấp cao nhất

- `backend/`: backend FastAPI/LangGraph hiện tại.
- `frontend/`: giao diện Next.js cho người dùng.
- `admin-frontend/`: giao diện Next.js riêng cho quản trị viên.
- `docker-compose.yml`: cấu hình chạy các service trên máy local.

## Cấu trúc backend

```text
backend/
├── pyproject.toml
├── Dockerfile
├── langgraph.json
├── src/app/
│   ├── main.py
│   ├── bootstrap.py
│   ├── api/
│   ├── core/
│   ├── orchestration/
│   ├── shared/
│   │   ├── contracts/
│   │   └── persistence/
│   └── modules/
│       ├── supervisor/
│       ├── explorer/
│       ├── information_finder/
│       ├── place_checker/
│       ├── itinerary_planner/
│       └── plan_editor/
└── tests/
```

`src/app/main.py` khởi tạo ứng dụng FastAPI. Thư mục `api/` định nghĩa ranh
giới HTTP. Thư mục `orchestration/` sở hữu root graph và ánh xạ các public
contract giữa các module. Business rule về du lịch không nên đặt trong
`orchestration/`.

## Ranh giới module

Mỗi module dọc có cấu trúc sau:

```text
modules/<module>/
├── public.py       # API import được module khác hỗ trợ
├── contract.py     # Pydantic contract công khai
├── state.py        # graph state nội bộ
├── graph.py        # factory tạo subgraph
├── nodes.py        # node LangGraph mỏng
├── service.py      # business logic xác định được
├── ports.py        # interface cho provider nếu cần
├── adapters/       # implementation provider cụ thể nếu cần
└── tests/          # test riêng của module
```

Module khác chỉ nên import thông qua `public.py`, không truy cập trực tiếp
state, node hoặc service nội bộ. Provider bên ngoài phải được đặt sau port và
adapter.

## Ranh giới API hiện tại

Backend hiện chỉ expose:

- `GET /health`
- `POST /v1/agent/invoke`

Endpoint agent nhận thread id, yêu cầu của người dùng, danh sách place tùy
chọn, itinerary hiện có và edit operation tùy chọn. Response trả về route đã
chọn, câu trả lời, itinerary nếu có, câu hỏi cần làm rõ và warning.

Authentication, Marketplace, import URL, lưu trữ bền vững, dữ liệu place live
và routing live chưa nằm trong scaffold hiện tại.
