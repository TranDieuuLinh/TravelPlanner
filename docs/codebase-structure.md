# Cấu trúc codebase hiện tại

Cập nhật lần cuối: 2026-08-11.

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
│       ├── plan_editor/
│       ├── auth/
│       └── knowledge_graph/
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

Authentication is implemented as a vertical `auth` module. It owns the
`auth_runtime_users` and `auth_runtime_sessions` tables, uses PostgreSQL when `DATABASE_URL` is
configured, and uses an in-memory repository only for tests or development
without a database. Sessions are opaque cookies; the raw token is never stored
in the database.

Information Finder hiện có service cache-first, các port `SearchProvider`,
`SourceRepository`, `EmbeddingProvider`, `SourceChunker`, `AnswerGenerator`,
adapter Tavily, Gemini URL Context chunker, Gemini embeddings và PostgreSQL/pgvector.
Các bảng do module sở hữu có tiền tố
`information_finder_`; module không dùng bảng legacy. Khi thiếu database hoặc
API key, development/test dùng fallback trung thực trong process.

Answer generator của Information Finder có thể nhận `LlmClient` dùng chung qua
dependency injection. Prompt, structured claim contract, source budget,
citation validation và fallback policy vẫn thuộc module Information Finder;
shared client chỉ sở hữu transport Gemini và key rotation.

Supervisor là intent classifier có provider cấu hình được. Khi provider là
`gemini`, mọi message được structured Gemini phân loại trước qua `shared/llm/`;
route `finish` có thể kèm phản hồi ngắn cùng ngôn ngữ cho greeting, câu hỏi về
trợ lý hoặc yêu cầu ngoài phạm vi. Rule deterministic chỉ là provider offline
hoặc runtime fallback. `SUPERVISOR_CLASSIFIER_PROVIDER=rules` chạy offline; cấu
hình `gemini` yêu cầu `GEMINI_API_KEY`. Routing baseline chưa
được production-evaluated.

`shared/llm/` cung cấp port và Gemini REST adapter dùng chung, bao gồm tùy chọn
URL Context tool cho module cần Gemini đọc URL public. `GEMINI_API_KEY`
là một chuỗi chứa nhiều key phân tách bằng dấu phẩy; adapter xoay vòng key và
cooldown key khi provider trả về lỗi có thể thử lại. Các agent hiện có chưa
được chuyển business behavior sang LLM ngoài Supervisor và Information Finder
theo cấu hình của từng module.

Authentication, Marketplace, import URL, dữ liệu place live và routing live
chưa nằm trong scaffold hiện tại. Checkpointer của root graph vẫn chưa bền vững.

## Cấu trúc style frontend

`frontend/src/app/globals.css` là entrypoint style duy nhất của app và chỉ giữ
các `@import`. CSS theo vùng chức năng nằm trong `frontend/src/styles/global/`,
được import theo đúng thứ tự cascade hiện tại; style riêng của Planner nằm trong
`frontend/src/features/planner/styles/`.

The existing planner UI remains the active entrypoint. Its API adapter in
`frontend/src/features/planner/api/plans.ts` maps the current `/v1/trip-chats`
contract to the existing view models without changing the planner layout.

`admin-frontend/app/globals.css` cũng chỉ giữ các import. Style admin được chia
theo shell/run, responsive, Knowledge Graph và AI import trong
`admin-frontend/styles/`; các panel Knowledge Graph nằm trong
`admin-frontend/app/components/knowledge-graph/`.
