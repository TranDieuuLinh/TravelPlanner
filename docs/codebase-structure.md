# Cấu trúc codebase hiện tại

Cập nhật lần cuối: 2026-08-14.

## Các ứng dụng cấp cao nhất

- `backend/`: backend FastAPI/LangGraph hiện tại.
- `frontend/`: giao diện Next.js cho người dùng.
- `admin-frontend/`: giao diện Next.js riêng cho quản trị viên.
- `packages/`: các package frontend dùng chung trong npm workspace; hiện có
  `api-client/` cho API error và request helper dùng chung.
- `docker-compose.yml`: cấu hình backend và routing service; database dùng
  `DATABASE_URL` bên ngoài, không tạo database local.

## Cấu trúc backend

```text
backend/
├── pyproject.toml
├── requirements.txt  # snapshot pin đầy đủ của backend/.venv
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
│   │   ├── llm/
│   │   └── tools/       # search, rating, daily/transport cost dùng chung
│   └── modules/
│       ├── supervisor/
│       ├── explorer/
│       ├── information_finder/
│       ├── place_checker/
│       ├── itinerary_planner/
│       ├── plan_editor/
│       ├── auth/
│       ├── conversation_memory/
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

Module `conversation_memory` đã hoàn thành Phase 01 & Phase 02. Module sở hữu public contract (`contract.py`), interfaces (`ports.py`), PostgreSQL asyncpg adapter (`adapters/postgres.py`), migration `009_conversation_memory.sql`, rule-based extractor (`extractor.py`), reference resolver (`resolver.py`), merge policy evaluator (`merge_policy.py`) và `ConversationMemoryService` (`service.py`) cung cấp `extract_facts`, `resolve_references`, `merge_extracted_facts` và `process_message`.


FinalItineraryPlanner đã bỏ scaffold round-robin/estimated routing. Graph của
module hiện chạy Phase 2 `prepare_problem` rồi Phase 3 global Valhalla matrix,
fallback đường chim bay khi Valhalla unavailable, và
sparse arcs trên contract `trip + places + food + accommodation`, sau đó chạy Phase 4 OR-Tools
CP-SAT ba pass để giữ tối đa `user_input`, tiếp đến URL rồi tối ưu utility.
Composition root inject Valhalla từ cấu hình cùng Xanh SM Hanoi fare estimator;
fallback đường chim bay được gắn tại provider boundary và luôn phát warning.
Fare estimator thuộc `shared/tools/transport_cost.py` để city-cost estimation
và Planner dùng cùng một policy/version thay vì sở hữu hai bảng giá.
Phase 5 lấy detail chỉ cho selected arcs, repair tối đa một vòng khi duration
thực tế phá timeline, rồi tạo public `ItineraryPlannerOutput`. Root/API trả nó
qua `plannerOutput`; legacy `itinerary` được giữ riêng cho PlanEditor. Root
orchestration không còn tạo lịch giả từ `VerifiedPlace` legacy.
Mỗi itinerary day có `costBreakdown` gồm accommodation, food, localTransport,
activities, misc và total trên một người. Planner điền giá stop, route và
Accommodation có giá do PlaceChecker chọn; misc giữ 0 khi chưa có dữ liệu thật.
Khi intake chưa có số phòng, accommodation tạm suy ra một phòng cho mỗi hai
khách rồi chia lại thành giá/người/ngày.
TripChat lưu hai snapshot độc lập: `currentItinerary` cho PlanEditor legacy và
`currentPlannerOutput` cho frontend hiển thị output mới. Frontend map
`days[].stops` thành item và `days[].legs` thành transport leg; guest planner
cũng gọi trực tiếp `POST /v1/agent/invoke` thay vì adapter plan legacy.
Danh sách TripChat chỉ map contract summary và giữ `hasItinerary`; sau một
message, frontend áp dụng trực tiếp full chat snapshot vừa nhận để chuyển sang
itinerary mà không phụ thuộc vào một lượt GET đồng bộ thứ hai. Output không có
ngày hoặc có ngày không chứa stop không được coi là `TravelPlan` hợp lệ.

## Ranh giới API hiện tại

Backend hiện chỉ expose:

- `GET /health`
- `POST /v1/agent/invoke`
- `GET/POST/DELETE /v1/trip-chats` và các endpoint message theo chat có auth

Endpoint agent nhận thread id, prompt tùy chọn, tối đa 20 URL, tối đa 20 ảnh,
`forceRefresh` tùy chọn,
itinerary hiện có và edit operation tùy chọn. Mỗi request phải có ít nhất một
trong prompt, URL hoặc ảnh. Ảnh JSON có thể mang `ocrText`; adapter OCR cho dữ
liệu `dataBase64` thô dùng shared Gemini client khi có key.

Explorer là LangGraph subgraph có hai route. Prompt-only trích xuất draft trực
tiếp. Source-import chạy URL và ảnh song song, đánh giá coverage trước khi tổng
hợp, rồi hai route hội tụ tại normalize, reconcile ADM và policy mặc định.
Khi source-import có raw prompt, prompt draft nhẹ và source synthesis chạy song
song rồi merge theo precedence để không làm mất tín hiệu rõ từ người dùng.
Success, clarification và failure lưu ba loại snapshot riêng; repository mặc
định vẫn là in-memory. Mỗi source tạo `SourceArtifact` nội bộ có loại evidence,
URL, time hint và thời điểm quan sát trước khi Gemini tổng hợp output. YouTube
ưu tiên đúng một track subtitle/automatic caption (`vi` rồi `en`) bằng
`yt-dlp --skip-download`, giữ toàn bộ timeline mà không tải video. Nếu không có
caption, adapter chỉ tải audio stream, chia mặc định thành chunk 5 phút có
overlap 5 giây và transcribe song song qua Gemini; media tạm bị xóa sau request.
Timestamp `t=`/`start=` chỉ ưu tiên chunk gần mốc đó vào hàng đợi trước; toàn bộ
caption/audio vẫn được xử lý.
TikTok ưu
tiên `curl-cffi` Safari đọc JSON
`__UNIVERSAL_DATA_FOR_REHYDRATION__`, lấy URL CDN thuộc allowlist và stream MP4
với giới hạn dung lượng; nếu HTML không có media mới fallback sang `yt-dlp`
theo thứ tự legacy standard, Chrome và Chrome 131/Android 14. Instagram vẫn
dùng chuỗi `yt-dlp` legacy. Không cần chuyển cookie từ frontend. OCR
lấy một frame mỗi 1,5 giây, giới hạn 72 frame và tối đa 10 ảnh trong mỗi batch
Gemini, còn audio chia ba chunk STT song song. Hai nhánh OCR/STT chạy đồng thời;
ffprobe bỏ qua OCR hoặc STT khi media không có video hoặc audio stream tương ứng.
Lỗi từng nhánh được giữ trong kết
quả source partial, ghi log theo code và đưa vào warning mà không làm mất
evidence của nhánh còn lại. Website dùng `httpx` và `trafilatura` để lấy
Markdown trước; HTTP block hoặc redirect quá giới hạn sẽ thử `curl-cffi` giả
lập Safari, sau đó mới fallback Playwright Chromium rồi tiếp tục qua
`trafilatura`. Nếu browser vẫn bị anti-bot
chặn, source thất bại cục bộ mà không làm hỏng source khác. TikTok/Instagram có thể yêu cầu cookie
Netscape qua `EXPLORER_YTDLP_COOKIE_FILE`.

Trước khi tải URL, Explorer tra cache PostgreSQL do module sở hữu trong bảng
`source_documents`, theo canonical URL, extractor version và TTL
`EXPLORER_URL_CACHE_TTL_SECONDS` (mặc định 7 ngày). Cache đọc được artifact
legacy v6; TikTok/Instagram/Facebook bỏ toàn bộ query khi tạo cache key để URL
được chia sẻ từ frontend vẫn khớp cùng video. Adapter ghi contract chuẩn hóa
version 8 cùng metadata coverage transcript; không lưu raw
third-party payload. `forceRefresh=true` bỏ qua cache lookup và cập nhật record
sau extraction. Lỗi đọc/ghi cache chỉ được log và không chặn extractor. Khi
không có `DATABASE_URL`, development/test dùng cache in-memory theo process.
Sau source extraction, Explorer cache `ExplorerDraft` đã tổng hợp trong bảng
`explorer_draft_cache`, keyed bằng prompt, evidence chuẩn hóa, namespace/model
và policy version. `EXPLORER_DRAFT_CACHE_TTL_SECONDS` mặc định 7 ngày;
`forceRefresh=true` bỏ qua và thay thế cả source cache lẫn draft cache.

Trong module Explorer, trách nhiệm được tách theo đúng lớp LangGraph:

- `graph.py` chỉ khai báo node, conditional edge và điểm hội tụ; factory nhận
  `ExplorerService` đã được inject, không khởi tạo adapter;
- `state.py` là `TypedDict` nội bộ, trong đó chỉ input ban đầu là bắt buộc;
- `nodes.py` là các hàm async mỏng: đọc/ghi state và gọi service;
- `service.py` sở hữu normalize, coverage, retry/error policy, precedence,
  completion gate và persistence policy;
- `ports.py` định nghĩa draft/source/cache/media/snapshot capability;
- `adapters/` triển khai provider cụ thể; composition mặc định chỉ diễn ra tại
  public boundary trong `public.py`.

Luồng compile hiện tại là `prepare_intake`, conditional edge sang prompt-only
hoặc source-import, rồi hội tụ tại `normalize_and_validate`,
`reconcile_input_adm`, `apply_defaults_and_precedence`, `completion_gate` và
snapshot kết quả tương ứng. Source-import chỉ gọi synthesis nếu batch coverage
còn evidence dùng được; mỗi source chỉ retry tối đa một lần.

Explorer chỉ trích xuất và giữ provenance, không resolve place. Root
orchestration chỉ chuyển output `ready` sang public input của PlaceChecker.
Explorer output mang `days`, `startDate` và `timezone`; mặc định duration là 3
ngày và ngày bắt đầu là ngày mai khi prompt không chỉ định.

Với rich PlaceChecker pipeline, root giữ `PlaceCheckerResult` cho diagnostic,
đồng thời dùng compact builder tạo `trip + places + food` và validate bằng
`ItineraryPlannerInput`. Payload nằm trong state `planner_input`; Planner runtime
tiêu thụ payload qua preprocessing, routing matrix, CP-SAT, route enrichment và
finalization.
Compact builder chỉ chuyển place/food có giá dùng được; `typical_cost` được lấy
từ trung bình khoảng min/max, một đầu mút có sẵn, hoặc `0` cho tier `free`.
`places[].sourcePlaces` phân biệt nguồn `input` và `url`; `sourceTimeHint` và
`addressHint` được giữ nhưng không có `sourceOrder` hay `sourceDay`.
Draft generator nằm sau port; prompt-only và source-import có provider cấu hình
riêng. Source-import chia từng source/artifact dài thành chunk khoảng 20.000 ký
tự; mỗi chunk gọi một structured Gemini request trả đồng thời place, ADM và
note. Mặc định ba chunk chạy song song, còn limiter dùng chung của Explorer giữ
tối đa sáu synthesis request đang chạy. Chunk thành công được giữ
khi chunk khác lỗi, rồi consolidation nhỏ merge alias/dịch thuật và lọc mention
không phải place.
Chunk structured-output lỗi lặp lại được chia đôi tối đa hai cấp; quota/cooldown
được retry có chờ và coverage vẫn được báo nếu provider chưa xử lý đủ.
Khi có source và Gemini key, structured Gemini synthesis lọc `urlNotes` chỉ giữ
chi tiết hữu ích có evidence như access/timing/price/caution, hoạt động cụ thể,
trải nghiệm đặc trưng hoặc fun fact; lời quảng cáo chung chung bị loại. Shared Gemini client xoay key
cho các lời gọi song song. Source synthesis dùng `GEMINI_MODEL`, frame/ảnh OCR
dùng `GEMINI_IMAGE_OCR_MODEL`, còn STT dùng `GEMINI_AUDIO_MODEL`.

Endpoint Explorer nhận trực tiếp `ExplorerInput`, bỏ qua root Supervisor,
PlaceChecker và Planner, rồi trả nguyên `ExplorerOutput`. Endpoint này dùng để
test/debug contract nhưng vẫn chạy cùng graph và provider configuration với
runtime.

Authentication is implemented as a vertical `auth` module. It owns the
`auth_runtime_users` and `auth_runtime_sessions` tables, uses PostgreSQL when `DATABASE_URL` is
configured, and uses an in-memory repository only for tests or development
without a database. Sessions are opaque cookies; the raw token is never stored
in the database.

Information Finder hiện có service cache-first, các port `SearchProvider`,
`SearchQueryPlanner`, `SourceRepository`, `EmbeddingProvider`, `SourceChunker`,
`AnswerGenerator`, adapter Tavily, LLM lập truy vấn tìm kiếm, Gemini URL Context
chunker, Gemini embeddings và PostgreSQL/pgvector.
Các bảng do module sở hữu có tiền tố
`information_finder_`; module không dùng bảng legacy. Khi thiếu database hoặc
API key, development/test dùng fallback trung thực trong process.

Answer generator của Information Finder có thể nhận `LlmClient` dùng chung qua
dependency injection. Prompt, structured claim contract, source budget,
citation validation và fallback policy vẫn thuộc module Information Finder;
shared client chỉ sở hữu transport Gemini và key rotation. Service lấy năm nguồn
local có điểm semantic cao nhất rồi truyền cho `LlmSearchQueryPlanner`; LLM chỉ
đặt `shouldSearch=true` và tạo tối đa ba truy vấn Tavily khi các nguồn này thiếu
dữ kiện cần thiết. Nếu planner lỗi, service chỉ dùng truy vấn deterministic khi
không có nguồn local hoặc cần refresh.
Answer generator trả về `entityCandidates` gồm tên hiển thị và các tên tra cứu,
bao gồm alias hoặc tên tiếng Anh khi có căn cứ. `KnowledgeGraphEntityResolver`
thử từng tên qua public Knowledge Graph contract và backend tự gắn
`travel-entity://entity` sau khi node tồn tại. Entity không resolve được không bị
gắn link giả.

Supervisor là intent classifier có provider cấu hình được. Khi provider là
`gemini`, mọi message được structured Gemini phân loại trước qua `shared/llm/`;
route `finish` có thể kèm phản hồi ngắn cùng ngôn ngữ cho greeting, câu hỏi về
trợ lý hoặc yêu cầu ngoài phạm vi. Rule deterministic chỉ là provider offline
hoặc runtime fallback. Supervisor hiện được cấu hình
`SUPERVISOR_CLASSIFIER_PROVIDER=gemini`; provider này yêu cầu `GEMINI_API_KEY`.
Routing baseline chưa
được production-evaluated. Root graph truyền tối đa sáu user message gần nhất
từ checkpoint làm context cho câu hỏi nối tiếp; đây chưa phải durable memory.
Itinerary Planner subgraph không kế thừa root checkpointer vì state tính toán
tạm thời chứa dataclass và immutable mappings; root chỉ checkpoint public input,
output và conversation state sau khi subgraph hoàn tất.

`shared/llm/` cung cấp port và Gemini REST adapter dùng chung, bao gồm tùy chọn
URL Context tool cho module cần Gemini đọc URL public. `GEMINI_API_KEY`
là một chuỗi chứa nhiều key phân tách bằng dấu phẩy. Text, OCR và audio client
dùng chung key pool với tối đa một request đang chạy trên mỗi key; mỗi request
chỉ thử tối đa ba key. Adapter vô hiệu hóa key bị từ chối, đọc `Retry-After`
cho lỗi 429, thêm jitter và cooldown lỗi có thể thử lại. Các agent hiện có chưa
được chuyển business behavior sang LLM ngoài Supervisor và Information Finder
theo cấu hình của từng module.

`shared/tools/search_places/` cung cấp engine async dùng chung để module gọi
qua dependency injection. Tool chuẩn hóa query, xếp hạng top-K, áp ngưỡng
identity/margin, chặn ADM/type/toạ độ không hợp lệ, giữ kết quả nhập nhằng để
review và chỉ fallback sang external provider khi Knowledge Graph miss hoặc
mọi match đều yếu. PlaceChecker runtime dùng `PostgresPlaceCatalog` khi có
`DATABASE_URL`: candidate generation được scope ADM/type, dùng top-K và toán tử
GIN `pg_trgm` trên canonical name, alias và relationship target trước khi tool
áp score cuối. Generic `travel place` discovery xen kẽ candidate
`Special_Experience` với các `TravelPlace` khác nằm trong đúng ADM; nhóm ngoài
special ưu tiên place có `Offer_Item -> ActivityItem`, metadata đầy đủ,
rating/review tốt. `Has_Style` không được dùng làm taxonomy/quota; nó chỉ cung
cấp fallback `time_duration` và `time_windows` khi place thiếu timing trực tiếp.
Compact PlaceChecker-to-Planner contract giữ `sourceKind`, ActivityItem IDs và
timing source. Planner phân period theo giờ stop thực tế, áp largest-remainder
70/30 cho morning và 60/40 cho evening bằng soft source-mix penalty, đồng thời
trả target/actual/fallback audit. Bayesian review quality tiếp tục xếp hạng độ
nổi tiếng trong objective sau các hard feasibility constraints.
Retrieval ngoài gap phân tích còn mở hai core pool có quota độc lập theo chuyến:
`12 TravelPlace/ngày` và `12 Restaurant/ngày`, tối đa 60 mỗi loại. Core query
over-fetch có giới hạn để bù candidate thiếu metadata; scoring chốt quota sau
dedupe và quality gate. Restaurant được compact builder đưa vào `food`, không
trộn thành activity place.
Compatibility graph không database vẫn dùng `DevelopmentCatalog`;
Google Maps/external live provider chưa được nối.
`shared/tools/bayesian_rating.py` cung cấp prior, adjusted rating, review
reliability và quality 0..1 dùng chung cho PlaceChecker và
FinalItineraryPlanner; module vẫn tự sở hữu cách đưa quality vào business score.
Candidate contract của tool giữ relationship evidence chuẩn hóa ở dạng dữ liệu
trung lập. PlaceChecker PostgreSQL adapter diễn giải `Special_Near`,
`Special_Experience`, `Offer_Item` và `Has_Style`, duyệt ADM đệ quy và chuyển
evidence có provenance sang scoring/output. Adapter không còn đọc `Near` legacy
hoặc `Must_Visit`. Timing mặc định của `Has_Style` được đọc từ properties của
node Style đích; timing riêng của place được ưu tiên.
Nhánh food selection riêng duyệt primary
`ADM -> Special_Experience -> FoodItem <- Special_Experience <- Restaurant <- Special_Near <- TravelPlace`.
Nó giữ tối đa một selection cho mỗi TravelPlace, chấp nhận quán duy nhất và dùng
Bayesian/review reliability để phân xử khi có nhiều quán. Query thuộc adapter,
thuật toán chọn thuộc service/tool của module.
Primary query chỉ nối bằng FoodItem ID chính xác, không dùng tên. Rich selection
giữ FoodItem, match type và confidence. Khi một anchor không có primary pair,
query dùng FoodItem trực tiếp từ `Restaurant -> Offer_Item` với match type
`offer_item_fallback`; fallback không ghi ngược, merge Knowledge Graph hoặc giả
làm món đặc trưng.
Identity acceptance mềm dành riêng
cho URL/direct input nằm trong `place_checker/resolution_policy.py`; policy này
không áp dụng cho system/retrieval candidate.

Authentication, Marketplace, URL import chịu được mọi anti-bot, dữ liệu place
live và routing live chưa nằm trong scaffold hiện tại. Checkpointer của root
graph vẫn chưa bền vững.

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
