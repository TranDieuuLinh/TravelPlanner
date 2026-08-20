# AGENTS.md

Đây là điểm bắt đầu dành cho coding agent làm việc với TravelPlanner. Phải đọc
file này trước khi thay đổi code.

Ngày cập nhật: 2026-08-20.

## Trạng thái backend hiện tại

Backend hiện tại là scaffold FastAPI/LangGraph theo kiến trúc module dọc
(vertical feature modules), chưa phải hệ thống dữ liệu du lịch production.

- Source code nằm trong `backend/src/app/`.
- API hiện có `GET /health` và `POST /v1/agent/invoke`.
- Root graph nằm trong `backend/src/app/orchestration/`.
- Các module hiện có: `supervisor`, `explorer`, `information_finder`,
  `place_checker`, `itinerary_planner` và `plan_editor`.
- Module khác chỉ được dùng public contract qua `public.py`; không truy cập
  trực tiếp state, node hoặc service nội bộ của module khác.
- Supervisor là classifier xác định tuyến xử lý.
- Explorer mới phân tích destination và duration từ input đơn giản.
- Information finder ưu tiên cache PostgreSQL/pgvector với Gemini embeddings, có Tavily Search qua
  cấu hình. Answer generator có thể dùng shared Gemini client với structured
  claims/citation validation; extractive vẫn là development/runtime fallback.
  Model baseline chưa được production-evaluated.
- Place checker dùng `DevelopmentCatalog`, chỉ tạo dữ liệu placeholder với
  `verified=false` và warning.
- Itinerary planner dùng estimated routing, chưa dùng dữ liệu đường thực tế.
- Checkpointer hiện lưu trong memory, cần durable storage trước khi production.
- Hiện chưa triển khai authentication, Marketplace, import URL, lưu trữ bền
  vững cho graph state, live place data và live routing.
- `backend/src/app/shared/` chỉ chứa contract/persistence dùng chung; repository
  `asyncpg` của Information Finder nằm trong chính module và chỉ sở hữu các bảng
  tiền tố `information_finder_`.

Không được mô tả tính năng mục tiêu hoặc placeholder như đã triển khai
production. Không đưa tuyên bố sai về trạng thái hệ thống vào UI, API docs,
README hoặc log.

## Quy tắc phạm vi sửa đổi

- Khi làm một module, chỉ sửa trong folder của module đó:
  `backend/src/app/modules/<module>/`.
- Không sửa file ngoài module nếu không cần thiết cho thay đổi.
- Nếu bắt buộc phải sửa ngoài module, phải xác định rõ lý do và chỉ sửa phần
  tối thiểu liên quan, thường là public contract, root orchestration, shared
  contract, API schema hoặc test integration.
- Không đưa business rule của module vào `api/`, `orchestration/` hoặc module
  khác. Root orchestration chỉ được điều phối và ánh xạ public contract.
- Test của module phải nằm trong `backend/src/app/modules/<module>/tests/`.
  Test graph/integration cấp backend nằm trong `backend/tests/`.

## Quy tắc tool và provider

- Tool, provider interface và adapter phải thuộc module sử dụng chúng.
- Đặt interface trong `ports.py`, implementation trong `adapters/`.
- Nếu module có nhiều tool hoặc tool cần tổ chức riêng, tạo
  `backend/src/app/modules/<module>/tools/` và đặt tool ở đó.
- Không tạo tool dùng riêng cho một module trong `shared/`, `api/` hoặc
  `orchestration/`.
- Chỉ đưa capability vào `shared/` khi thực sự dùng chung bởi nhiều module và
  không chứa business rule riêng của module nào.
- External capability phải đi qua port/interface; không gọi provider trực tiếp
  từ graph node nếu có thể tách adapter.
- Importer không được truyền raw payload của nguồn vào Planner. Dữ liệu phải
  được chuẩn hóa thành contract có provenance trước khi vào module tiếp theo.

## Quy tắc tag JSON

- Trước khi thay đổi, kiểm tra hoặc đưa ví dụ JSON có field `tags`, phải đọc
  lại `auto-attach/tags-auto.yml` trong chính worktree hiện tại.
- Mọi giá trị xuất hiện trong `tags` của JSON public phải là key hiện có trong
  `tags-auto.yml`; không tự tạo tag mới hoặc hard-code bản sao của từ điển vào
  source code.
- Runtime phải dùng `tags-auto.yml` làm source of truth và nhận thay đổi của
  file mà không cần restart backend.

## Kiến trúc backend

- Backend dùng FastAPI và LangGraph, package root là `backend/src`.
- Cấu trúc chính:

  ```text
  backend/src/app/
  ├── api/              # HTTP boundary và API schema
  ├── core/             # config và lỗi dùng ở cấp ứng dụng
  ├── orchestration/    # root graph, route và ánh xạ public contract
  ├── shared/           # contract/persistence thật sự dùng chung
  └── modules/<module>/ # vertical feature module
  ```

- Module nên có cấu trúc:

  ```text
  modules/<module>/
  ├── public.py         # API import được module khác hỗ trợ
  ├── contract.py       # Pydantic input/output contract
  ├── state.py          # LangGraph state nội bộ
  ├── graph.py          # factory tạo subgraph
  ├── nodes.py          # node LangGraph mỏng
  ├── service.py        # business behavior xác định được
  ├── ports.py          # provider interface nếu cần
  ├── adapters/         # provider implementation cụ thể nếu cần
  ├── tools/            # tool riêng của module nếu cần
  └── tests/             # test riêng của module
  ```

- Business rule phải nằm trong module hoặc service của module, không đặt trong
  FastAPI router hay root orchestration.
- JSON bên ngoài dùng camelCase; Python dùng snake_case.
- Module chỉ expose contract/API được hỗ trợ qua `public.py`.
- Không mặc định coi database legacy hiện có là backend runtime. Chỉ kết nối
  database hoặc thêm migration khi đã xác định rõ ownership, database đích,
  repository và tài liệu liên quan.
- Dữ liệu bên ngoài phải lưu provenance và độ mới khi feature đó được triển khai.
- Plan đã mua phải là bản sao cá nhân; chỉnh sửa bản sao không được thay đổi
  phiên bản creator đã xuất bản.
- Backup plan là plan riêng liên kết với main plan; không âm thầm ghi đè main
  plan đã khóa.

## Quy tắc tài liệu và ngày cập nhật

- Tài liệu có tên bắt đầu bằng số là tài liệu theo thứ tự ưu tiên/roadmap; không
  tự ý đổi số hoặc đổi tên nếu chưa có lý do rõ ràng.
- Khi thay đổi behavior, contract, cấu trúc hoặc phạm vi được mô tả trong tài
  liệu, phải cập nhật tài liệu liên quan trong cùng thay đổi.
- Khi sửa nội dung liên quan đến file không có tiền tố số, phải cập nhật trường
  ngày sửa đổi trong chính file đó theo định dạng `YYYY-MM-DD`. Nếu file chưa có
  trường này, thêm `Cập nhật lần cuối: YYYY-MM-DD` ở phần đầu tài liệu.
- Ít nhất phải xem tài liệu liên quan sau khi thay đổi: `docs/codebase-structure.md`,
  `docs/schema.md` và `docs/database-schema.md` cho thay đổi backend/schema.
- Không ghi secret, dữ liệu cá nhân, raw third-party payload hoặc toàn bộ prompt
  vào tài liệu, source code hay log.

## Giới hạn kích thước file

- Với backend, không để file source, test hoặc tài liệu vượt quá 400 dòng nếu có
  thể tách nhỏ.
- Khi file backend tiến gần hoặc vượt 400 dòng, tách theo trách nhiệm:
  contract/schema, state, node, service, adapter/tool hoặc test case.
- Với frontend, không áp dụng cứng giới hạn 400 dòng. Frontend phải được gom theo
  tính năng và chức năng, giữ cho mỗi module/feature có ranh giới rõ ràng.
- Nếu file frontend quá dài, khó đọc hoặc chứa quá nhiều trách nhiệm, phải đánh
  giá refactor. Có thể hỏi lại người dùng trước khi thực hiện refactor lớn hoặc
  thay đổi cấu trúc feature.
- Không tách máy móc làm vỡ ranh giới module/feature; file mới vẫn phải nằm trong
  đúng phạm vi và giữ public API rõ ràng.
- Sau khi sửa, kiểm tra kích thước và mức độ tập trung trách nhiệm của các file
  thay đổi; backend phải tuân thủ giới hạn 400 dòng, frontend phải tuân thủ ranh
  giới tính năng/chức năng.

## Checklist trước khi sửa

1. Xác định module sở hữu behavior cần thay đổi.
2. Đọc `public.py`, contract, graph, service, ports/adapters/tools và tests của
   module đó.
3. Kiểm tra API/orchestration/shared contract có thật sự cần sửa không.
4. Đọc tài liệu backend và schema liên quan.
5. Kiểm tra kích thước các file dự kiến sửa.

## Checklist trước khi hoàn thành

1. Chạy test sát module; chạy integration test nếu thay đổi root graph hoặc API.
2. Chạy `python -m compileall src` và type/contract checks phù hợp nếu có.
3. Kiểm tra success flow, error flow và boundary giữa các module.
4. Cập nhật tài liệu và ngày sửa đổi khi contract, cấu trúc hoặc phạm vi thay đổi.
5. Kiểm tra không có file thay đổi ngoài module nếu không có lý do cần thiết.
6. Kiểm tra không có file source, test hoặc tài liệu vượt 400 dòng nếu có thể
   tách nhỏ.
7. Thêm ADR khi chọn provider hoặc quyết định kiến trúc khó đảo ngược.

## Lệnh backend thường dùng

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
python -m compileall src
```

LangGraph Studio có thể load graph trong `backend/langgraph.json` sau khi cài
LangGraph CLI.
