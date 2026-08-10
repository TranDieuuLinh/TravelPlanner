# Cấu trúc codebase hiện tại

Cập nhật lần cuối: 2026-08-10.

## Các ứng dụng cấp cao nhất

- `backend/`: backend FastAPI/LangGraph hiện tại.
- `frontend/`: giao diện Next.js cho người dùng.
- `admin-frontend/`: giao diện Next.js riêng cho quản trị viên.
- `packages/`: các package frontend dùng chung trong npm workspace; hiện có
  `api-client/` cho API error và request helper dùng chung.
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
│   │   ├── persistence/
│   │   └── llm/
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

Information Finder hiện có service cache-first, các port `SearchProvider`,
`SourceRepository`, `EmbeddingProvider`, `AnswerGenerator`, adapter Tavily,
multilingual-e5 và PostgreSQL/pgvector. Các bảng do module sở hữu có tiền tố
`information_finder_`; module không dùng bảng legacy. Khi thiếu database hoặc
API key, development/test dùng fallback trung thực trong process.

`shared/llm/` cung cấp port và Gemini REST adapter dùng chung. `GEMINI_API_KEY`
là một chuỗi chứa nhiều key phân tách bằng dấu phẩy; adapter xoay vòng key và
cooldown key khi provider trả về lỗi có thể thử lại. Các agent hiện có chưa
được chuyển business behavior sang LLM.

Authentication, Marketplace, import URL, dữ liệu place live và routing live
chưa nằm trong scaffold hiện tại. Checkpointer của root graph vẫn chưa bền vững.
