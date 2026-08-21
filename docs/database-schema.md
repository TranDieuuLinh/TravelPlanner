# Database schema thực tế

Cập nhật lần cuối: 2026-08-21.

## Phạm vi và trạng thái

Tài liệu này mô tả schema PostgreSQL có pgvector được backend truy cập qua
`DATABASE_URL`. PostgreSQL là dependency bên ngoài Compose: có thể là database
local đã chạy trên host hoặc database cloud. Compose không tải image, khởi tạo
database hay sở hữu volume PostgreSQL; database được chọn hoàn toàn bằng
`DATABASE_URL` trong `backend/.env`.

Khi backend chạy trong Docker và PostgreSQL chạy trên máy host, hostname trong
URL là `host.docker.internal`. Khi cả backend và PostgreSQL cùng chạy trực tiếp
trên host, dùng `localhost`. Với cloud, dùng hostname và TLS options do provider
cung cấp. Trong cả ba trường hợp, database phải được tạo sẵn và áp dụng các
migration cần thiết trước khi khởi động backend.

Database runtime hiện có 59 table trong schema `public`, gồm các bảng cache, planner,
Knowledge Graph, profile, social và marketplace được
khôi phục từ export ngày 2026-08-11 và 6 table cache của Information Finder.
Bốn table tag legacy (`knowledge_tags`, `knowledge_tag_runs`,
`knowledge_tag_scan_results`, `knowledge_entity_tag_assertions`) đã được xóa.
Các migration bổ sung `007_legacy_runtime_schema.sql` và
`008_marketplace_social_schema.sql` mô tả các bảng runtime/legacy còn lại, theo
đúng thứ tự dependency. Backend LangGraph mới trong `backend/src/app` không có SQLAlchemy model để đọc
các table legacy. Information Finder có repository `asyncpg` và migration SQL
riêng, chỉ sở hữu các bảng tiền tố `information_finder_`. Explorer đã nhận
ownership bảng `source_documents` và `explorer_draft_cache` qua asyncpg adapter
và migration 002/003. Vì vậy
cần phân biệt:

- **Database runtime:** các table được liệt kê bên dưới tồn tại trong database
  PostgreSQL đã chọn sau khi migration tương ứng được áp dụng; database local có
  thể được khôi phục từ backup archive tương ứng nhưng không do Compose quản lý.
- **Backend mới:** không sử dụng các table legacy khác; khi có `DATABASE_URL`,
  root graph dùng PostgreSQL checkpointer và fail fast nếu runtime psycopg không
  khả dụng. Chỉ môi trường không cấu hình database mới dùng `InMemorySaver`.
  Explorer dùng `source_documents` và `explorer_draft_cache`;
  Information Finder dùng
  các bảng cache mô tả bên dưới khi có `DATABASE_URL` và migration tương ứng đã
  được áp dụng.

PlaceChecker hiện nối `PostgresPlaceCatalog` read-only vào bốn bảng Knowledge
Graph core khi có `DATABASE_URL`. Candidate generation được scope ADM/type,
dùng top-K cùng toán tử `pg_trgm` `%` trên `normalized_name`,
`normalized_alias` và tên target relationship. Các GIN trigram index từ
migration 006 phục vụ prefilter; `SearchPlacesTool` vẫn sở hữu score và
acceptance policy cuối. Adapter không ghi Knowledge Graph và external live
provider chưa được nối. Migration 015 curates một tập ID Hà Nội đã review:
venue nghệ thuật/trải nghiệm được đổi sang `Entertainment`, còn shop, showroom,
trường/lớp và dịch vụ không phù hợp được gắn property
`generic_discovery_excluded=true`. PlaceChecker chỉ áp cờ này cho generic
discovery; named-place lookup vẫn resolve entity khi user gọi đúng tên, và night
market vẫn là `TravelPlace`.
Migration 016 áp batch review tiếp theo, sửa chiều type cho venue/landmark/quán
ăn, gắn cờ loại generic cho tám dịch vụ thương mại và làm sạch identity Trung
tâm Văn hóa Kim Đồng. Record Kim Đồng được chuyển về Hàng Bài/Hoàn Kiếm theo
OpenStreetMap way `863234970`; alias, tọa độ và mô tả được thay bằng dữ liệu đã
review, còn rating, ảnh, giờ mở cửa, Google metadata và `Special_Near` sinh từ
record cửa hàng sai được xóa để chờ nguồn đúng.
Migration 017 bổ sung 62 alias Việt/Anh/tên gọi phổ biến cho 20 địa điểm đứng
đầu pool Hà Nội, đồng thời chỉ xóa 20 alias mojibake hoặc sai đã xác định. Ví dụ
`36 phố phường` resolve về `Hanoi Old Quarter`; alias sai `Hồ Con Rùa` bị gỡ
khỏi Hồ Hoàn Kiếm. Một record Hoàng thành pending trùng địa chỉ, tọa độ và
rating với entity chính được giữ lại nhưng chuyển `status=rejected` để lookup
không trả duplicate.
Migration 018 mở rộng audit tới top 60 TravelPlace hiện tại: upsert 79 alias
Việt/Anh đã review và xóa chọn lọc 40 alias mojibake của đúng các entity liên
quan. Migration này chỉ sửa `knowledge_aliases`; không đổi entity type, status
hoặc cờ generic discovery. Named lookup kiểm tra được 35/35 tên gọi về đúng địa
điểm vật lý; 34/35 về đúng canonical ID do `Đền Bạch Mã` còn một pending entity
trùng địa chỉ và tọa độ cần xử lý bằng quy trình dedupe riêng.

FinalItineraryPlanner Phase 5 không thêm table hoặc migration. Global matrix,
CP-SAT result, selected route detail và `ItineraryPlannerOutput` chỉ tồn tại
trong graph state/request hiện tại; việc lưu plan production vẫn phải đi qua
trip-chat/revision ownership riêng, không ghi trực tiếp từ Planner.
`excludedCandidates`, accommodation route geometry và solver audit metadata
cũng chỉ là contract/runtime state, không tạo thêm database ownership.
Beam Search evaluation và `MatrixCell.food_to_food` cũng là dữ liệu dẫn xuất
trong graph state/request, không tạo bảng hoặc migration mới.

Observability thay đổi hiện tại không thêm table hoặc migration. Trace được giữ
tối đa 500 request trong snapshot cục bộ
`backend/logs/observability/traces.json`; đây là diagnostic theo process, không
phải durable database tracing và không an toàn cho mô hình nhiều worker cùng
ghi. Mỗi trace dùng request UUID riêng, còn `thread_id` chỉ dùng để nhóm session.

Explorer có ba loại snapshot logic: `ready`, `clarification` và `failure`.
Thay đổi hiện tại dùng `InMemoryExplorerSnapshotRepository`, không tạo table
hay migration và không ghi raw prompt/raw third-party payload. Trước production
cần xác định database ownership rồi triển khai durable adapter cho port
`ExplorerSnapshotRepository`; lỗi lưu snapshot không được phép đi tiếp sang
PlaceChecker.
`TripContextPatch` cho các operation set/add/remove chỉ tồn tại trong graph state
của lượt hiện tại. `pending_explorer_review` và `pending_explorer_output` được
root checkpointer giữ theo `threadId` giữa lượt hỏi mặc định và lượt user sửa;
chúng không dùng bảng Conversation Memory và thay đổi handoff này không thêm
table, column hoặc migration.
Payload sang PlaceChecker không lưu place tags/confidence hay provenance nội bộ.
YouTube/Instagram importer dùng `yt-dlp`; TikTok đọc HTML Safari. URL media đánh
giá transcript/metadata/description trước và chỉ tải media CDN để chạy OCR/STT
khi primary evidence chưa đủ; policy này không thêm bảng hoặc cột. Website dùng
`httpx`, `curl-cffi`, fallback Playwright và `trafilatura`; OCR/STT dùng Gemini.
Migration
`002_explorer_source_document_cache.sql` nhận ownership bảng
`source_documents`. Cache chỉ lưu `SourceArtifact` đã chuẩn hóa và lỗi nhánh
gọn; media tạm và raw third-party payload không được lưu. Media tạm được xóa
sau extraction và snapshot chỉ nhận Explorer output đã chuẩn hóa cùng
provenance.

Migration `003_explorer_draft_cache.sql` tạo `explorer_draft_cache`. Bảng lưu
`ExplorerDraft` đã chuẩn hóa theo hash của prompt và evidence, namespace/model,
TTL ứng dụng; không lưu media hoặc raw third-party payload. Structured draft
hiện có thêm tín hiệu `days`, `startDate`, `peopleExplicit` và
`preferencesExplicit`; namespace cache được tăng lên `v4` để không tái dùng
payload cũ thiếu các field này. Đây là thay đổi JSON payload/namespace, không
thêm table, column hoặc migration.

Timeout theo source/chunk, lịch round-robin và fallback tiêu đề Markdown chỉ là
runtime policy. Thay đổi này không thêm bảng/cột và không thay đổi ownership của
`source_documents` hoặc `explorer_draft_cache`.

## Schema cache nguồn Information Finder

Migration nguồn: `backend/migrations/001_information_finder_source_cache.sql`.
Migration đã được áp dụng thủ công vào volume runtime ngày 2026-08-11 sau khi
tạo backup. Docker vẫn chỉ tự áp migration khi khởi tạo volume mới; volume hiện
hữu khác cần chạy migration thủ công và kiểm tra backup trước.

| Bảng | Trách nhiệm chính |
|---|---|
| `information_finder_source_documents` | Canonical URL duy nhất, domain, title, provider và `review_status` mặc định `pending`. |
| `information_finder_source_snapshots` | Nội dung theo content hash; phân biệt `published_at`, `source_updated_at`, `last_fetched_at`, `expires_at` và provenance Tavily. |
| `information_finder_source_chunks` | Semantic chunk từ Gemini URL Context (được giới hạn theo số từ) hoặc fallback khoảng 300 từ/overlap 50 từ; có generated `tsvector`. Phiên bản chunking nằm ở `source_snapshots.extractor_version`. |
| `information_finder_source_embeddings` | Vector 384 chiều cùng model, revision, dimensions và `embedded_at`. |
| `information_finder_search_runs` | Query gốc/chuẩn hóa, tham số, request id, trạng thái và lỗi provider. |
| `information_finder_search_run_sources` | Snapshot thuộc search run, rank, provider score và snippet. |

Unique constraint chống trùng canonical URL, snapshot content hash, chunk và
embedding model/revision. Ghi search run và nguồn dùng một transaction; lời gọi
Tavily và embedding không giữ transaction mở. Đây là source cache runtime, không
phải bằng chứng admin đã review dữ liệu.

Các kiểu `json` lưu dữ liệu JSON; `timestamptz` là thời điểm có timezone; `NULL`
là cột cho phép không có giá trị. Mô tả cột dưới đây là mô tả ngắn theo tên và
metadata thực tế của database.

## Bảng hệ thống

### `alembic_version`

Ngày sửa đổi cuối cùng: 2026-08-10 (metadata được đọc từ database).

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `version_num` | varchar | Không | Revision Alembic hiện tại. |

### `audit_events`

Ngày sửa đổi cuối cùng: 2026-08-14.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã sự kiện audit. |
| `actor_id` | integer | Có | User thực hiện hành động. |
| `action` | varchar | Không | Loại hành động. |
| `resource_type` | varchar | Không | Loại resource bị tác động. |
| `resource_id` | varchar | Có | Mã resource bị tác động. |
| `request_id` | varchar | Có | Mã request liên quan. |
| `metadata` | json | Không | Metadata của sự kiện. |
| `created_at` | timestamptz | Không | Thời điểm tạo sự kiện. |

### `auth_runtime_sessions`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | integer | Không | Khóa chính session. |
| `user_id` | integer | Không | User sở hữu session. |
| `token_hash` | varchar | Không | SHA-256 hash của refresh JWT. |
| `csrf_token_hash` | varchar | Không | Hash của CSRF token dùng cho refresh/logout. |
| `expires_at` | timestamptz | Không | Thời điểm session hết hạn. |
| `last_used_at` | timestamptz | Có | Lần cuối refresh session được dùng. |

### `users`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | integer | Không | Mã user. |
| `email` | varchar | Không | Email đăng nhập. |
| `full_name` | varchar | Không | Tên hiển thị. |
| `role` | varchar | Không | Vai trò user. |
| `avatar_url` | varchar | Có | URL ảnh đại diện. |
| `created_at` | timestamptz | Không | Thời điểm tạo user. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

| `status` | varchar | Không | Trạng thái tài khoản. |
| `password_hash` | varchar | Có | Hash mật khẩu. |
| `bio` | text | Có | Giới thiệu user. |
| `creator_status` | varchar | Không | Trạng thái creator. |
| `creator_portfolio_urls` | json | Không | Danh sách URL portfolio. |

## Bảng planner và hội thoại

### `trip_chats`

The legacy `trip_chats` tables documented below are not used by the current
agent planner. The current runtime owns the isolated tables below instead.

### `agent_trip_chats`

Stores the authenticated user's chat id, LangGraph `thread_id`, revision and
two independent latest-plan snapshots. `current_itinerary` is the legacy
PlanEditor JSON created by `backend/migrations/003_trip_chat.sql`;
`current_planner_output` is the FinalItineraryPlanner JSON added by
`backend/migrations/009_trip_chat_planner_output.sql`. A chat update uses the
new non-null output and otherwise preserves the previous snapshot.
List-chat queries are bounded (30 records by default) and project only whether
a plan snapshot exists. The large JSONB snapshots are fetched only when opening
one chat through the detail/bootstrap contract; no migration is required for
this query-level optimization. The existing `(user_id, updated_at DESC)` index
continues to serve the bounded recent-chat lookup.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `current_itinerary` | jsonb | Có | Snapshot legacy dành cho PlanEditor. |
| `current_planner_output` | jsonb | Có | Output mới gồm `people`, `days[].stops` và `days[].legs`. |

Stop trong snapshot giữ hai vùng note độc lập: `notes` là object chỉ đọc gồm
`text`, `sourceType`, `sourceUrl`; `personalNotes` là chuỗi do user sở hữu.
Accommodation trong cùng JSONB snapshot cũng có thể giữ `personalNotes`. Các
thao tác sửa/xóa accommodation dùng optimistic revision trên hàng
`agent_trip_chats`; không cần thêm cột hoặc migration.
Thao tác thay một địa điểm chạy day repair trước khi ghi; sau khi route/timeline
khả thi, backend thay toàn bộ `current_planner_output` bằng một câu UPDATE có
điều kiện revision. Vì stop, giờ và leg vẫn nằm trong JSONB hiện hữu nên feature
này không cần bảng, cột hoặc migration mới.
Lệnh thêm/sửa/xóa/sắp xếp bằng ngôn ngữ tự nhiên không tạo persistence path
mới. Supervisor trả structured `planEdit` trong cùng Gemini call dùng để route,
sau đó Trip Chat gọi lại mutation hiện có trên `current_planner_output`. Adapter
PostgreSQL khóa hàng theo optimistic revision rồi cập nhật JSONB và chèn cặp
message user/assistant trong cùng transaction, vì vậy một lượt sửa chỉ tăng
revision một lần. Structured interpretation không được lưu riêng và thay đổi
này không cần bảng, cột hoặc migration mới.
Note đã liên kết từ raw prompt được ghi vào `personalNotes`. Object `notes` chỉ
chứa source note read-only và chọn URL trước Google Maps/Knowledge Graph; URL
thật dùng `sourceType=url`. Cả hai field đều nằm trong JSONB hiện hữu nên không
cần migration. Với Google Maps/Knowledge Graph note đã chọn, Place Checker tạo
bản tiếng Việt trong execution trước khi Planner ghi snapshot; `sourceType` và
`sourceUrl` được giữ nguyên. Cache bản dịch hiện nằm trong process và không ghi
đè property `description` gốc của Knowledge Graph, nên thay đổi này cũng không
thêm bảng hoặc cột.
Thay đổi ghi chú cá nhân cập nhật nguyên tử chính JSONB này với optimistic
revision; không có bảng note riêng và không lưu raw payload từ URL hoặc Google
Maps. Source note không Việt hóa được sẽ bị bỏ khỏi snapshot thay vì lưu chuỗi
tiếng Anh để frontend hiển thị.
Lựa chọn phương tiện của user được lưu dưới
`current_planner_output.days[].legs[].selectedTransport` trong cùng JSONB.
Mutation khóa row, kiểm tra revision rồi tăng revision; không cần thêm table
hoặc migration và chỉ lưu option routing đã chuẩn hóa, không lưu raw provider
payload.
Quy mô nhóm được lưu tại `current_planner_output.people`; đây là field trong
JSONB hiện hữu nên thay đổi không cần migration hoặc cột mới.
Entry `current_planner_output.unscheduled` cũng thuộc snapshot JSONB hiện hữu.
Mutation xác nhận một match khóa row, thêm stop vào ngày đích, xóa entry tương
ứng và tăng revision trong cùng transaction; mutation xóa chỉ xóa entry đó.
Hai thao tác không tạo bảng hoặc migration mới.

### `agent_trip_chat_messages`

Stores ordered user/assistant messages, route metadata, warnings and sources.
Rows cascade with their owning `agent_trip_chats` record.

Migration `008_trip_chat_content_blocks.sql` bổ sung cột `content_blocks`
kiểu `jsonb`, mặc định `[]`. Cột này lưu structured answer riêng với cột
`content`; message cũ khi đọc được chuẩn hóa thành danh sách rỗng.

### `agent_conversation_memory`

Cập nhật lần cuối: 2026-08-17. Bảng do module `conversation_memory` sở hữu; migration là `backend/migrations/009_conversation_memory.sql`. Lưu working memory state theo `chat_id` và `user_id` với optimistic concurrency control (`version`).

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `chat_id` | text | Không | Khóa chính, mã cuộc trò chuyện. |
| `user_id` | integer | Không | Mã user sở hữu cuộc trò chuyện. |
| `destination` | text | Có | Điểm đến chính. |
| `duration_days` | integer | Có | Số ngày du lịch. |
| `travelers` | integer | Có | Số lượng khách du lịch (1..50). |
| `budget` | jsonb | Không | Cấu trúc hoặc mức ngân sách. |
| `preferences` | jsonb | Không | Danh sách sở thích. |
| `avoids` | jsonb | Không | Danh sách điểm/yếu tố cần tránh. |
| `mentioned_places` | jsonb | Không | Các địa điểm đã được nhắc tới. |
| `selected_places` | jsonb | Không | Các địa điểm user đã chọn/xác nhận. |
| `active_references` | jsonb | Không | Các tham chiếu ngôn ngữ đã resolve hoặc đang chờ làm rõ. |
| `current_plan_ref` | text | Có | Mã tham chiếu tới plan hiện tại. |
| `pending_goal` | text | Có | Ý định/mục tiêu chưa hoàn thành. |
| `last_route` | varchar | Có | Route của supervisor/agent gần nhất. |
| `summary` | text | Có | Tóm tắt rolling ngữ cảnh hội thoại. |
| `version` | integer | Không | Optimistic concurrency version (>= 0). |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Thời điểm cập nhật gần nhất. |

### `agent_conversation_memory_facts`

Cập nhật lần cuối: 2026-08-17. Bảng do module `conversation_memory` sở hữu; migration là `backend/migrations/009_conversation_memory.sql`. Lưu thông tin chi tiết từng memory fact với provenance và trạng thái audit (`active`, `superseded`, `expired`, `rejected`). `fact_id` ổn định theo message để retry idempotent; repository chỉ upsert khi fact hiện có thuộc đúng cùng `chat_id` và `user_id`.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `fact_id` | text | Không | Khóa chính fact. |
| `chat_id` | text | Không | FK tới `agent_conversation_memory`. |
| `user_id` | integer | Không | Mã user sở hữu. |
| `fact_type` | varchar | Không | Loại fact (`destination`, `duration`, ...). |
| `key` | varchar | Không | Tên khóa dữ liệu. |
| `value` | jsonb | Không | Giá trị fact dạng JSON. |
| `normalized_value` | text | Không | Chuỗi giá trị chuẩn hóa (trim, lowercase, collapse whitespace) cho deduplication. |
| `value_type` | varchar | Không | Kiểu dữ liệu (`string`, `int`, `list`, ...). |
| `scope` | varchar | Không | Phạm vi fact (`chat`, `user`). |
| `status` | varchar | Không | Trạng thái (`active`, `superseded`, ...). |
| `confirmed_by_user` | boolean | Không | Đã được user xác nhận trực tiếp hay chưa. |
| `confidence` | float8 | Không | Độ tin cậy trích xuất [0.0, 1.0]. |
| `source_turn` | integer | Không | Lượt hội thoại trích xuất. |
| `source_excerpt` | varchar(200) | Không | Đoạn trích dẫn ngắn (tối đa 200 ký tự). |
| `source_message_id` | text | Có | Mã message trong transcript. |
| `source_url` | varchar(500) | Có | URL nguồn chứa dữ liệu trích xuất. |
| `extracted_by` | varchar | Không | Tên dịch vụ trích xuất. |
| `observed_at` | timestamptz | Không | Thời điểm quan sát. |
| `expires_at` | timestamptz | Có | Thời điểm hết hạn. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Thời điểm cập nhật gần nhất. |

Phase 05 thêm migration `010_phase05_memory_durable.sql`: index truy vấn
user-scoped preference, hàm retention có chủ đích cho fact đã `superseded` hoặc
`rejected`, và để `AsyncPostgresSaver.setup()` tạo/upgrade các bảng checkpoint
của LangGraph.


Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã cuộc trò chuyện. |
| `user_id` | integer | Không | User sở hữu cuộc trò chuyện. |
| `title` | varchar | Không | Tiêu đề cuộc trò chuyện. |
| `destination` | varchar | Có | Điểm đến hiện tại. |
| `current_plan` | json | Có | Plan hiện tại dạng JSON. |
| `current_intake_id` | varchar | Có | Mã intake hiện tại. |
| `revision` | integer | Không | Revision hiện tại của plan. |
| `created_at` | timestamptz | Không | Thời điểm tạo chat. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `latest_explorer_timing` | json | Có | Timing lần Explorer gần nhất. |
| `latest_planner_timing` | json | Có | Timing lần Planner gần nhất. |
| `conversation_phase` | varchar | Không | Giai đoạn hội thoại. |
| `conversation_context` | json | Không | Context hội thoại. |
| `active_pending_turn_id` | varchar | Có | Turn đang chờ xử lý. |
| `current_trip_intent` | json | Có | Trip intent hiện tại. |
| `trip_intent_version` | integer | Không | Version của trip intent. |
| `trip_intent_plan_status` | varchar | Không | Trạng thái đồng bộ intent với plan. |

### `trip_chat_messages`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã message. |
| `chat_id` | varchar | Không | Chat chứa message. |
| `role` | varchar | Không | Vai trò người gửi. |
| `content` | text | Không | Nội dung message. |
| `sequence` | integer | Không | Thứ tự message. |
| `attachment_names` | json | Không | Tên file đính kèm. |
| `plan_revision` | integer | Có | Revision plan liên quan. |
| `created_at` | timestamptz | Không | Thời điểm tạo message. |
| `turn_id` | varchar | Có | Mã turn xử lý. |
| `message_kind` | varchar | Không | Loại message. |
| `content_blocks` | json | Không | Các block nội dung. |
| `client_turn_id` | varchar | Có | Mã turn từ client. |
| `base_revision` | integer | Có | Revision làm cơ sở. |
| `status` | varchar | Có | Trạng thái xử lý. |
| `intent` | varchar | Có | Intent được phân loại. |
| `confidence` | float8 | Có | Độ tin cậy phân loại. |
| `requires_confirmation` | boolean | Không | Có cần user xác nhận không. |
| `proposed_operations` | json | Không | Các operation đề xuất. |
| `assistant_blocks` | json | Không | Block response của assistant. |
| `result_summary` | json | Không | Tóm tắt kết quả xử lý. |
| `error_code` | varchar | Có | Mã lỗi nếu thất bại. |
| `error_message` | text | Có | Nội dung lỗi nếu thất bại. |
| `processing_started_at` | timestamptz | Có | Thời điểm bắt đầu xử lý. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `trip_revisions`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã revision. |
| `chat_id` | varchar | Không | Chat sở hữu revision. |
| `revision` | integer | Không | Số revision. |
| `plan_payload` | json | Không | Snapshot plan. |
| `created_at` | timestamptz | Không | Thời điểm tạo revision. |
| `intake_id` | varchar | Có | Intake tạo revision. |
| `trip_intent_payload` | json | Có | Snapshot trip intent. |

### `planning_runs`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã planning run. |
| `user_id` | integer | Có | User khởi tạo run. |
| `intake_id` | varchar | Có | Intake liên quan. |
| `source` | varchar | Không | Nguồn yêu cầu. |
| `mode` | varchar | Không | Chế độ chạy planner. |
| `destination` | varchar | Không | Điểm đến được xử lý. |
| `status` | varchar | Không | Trạng thái run. |
| `current_stage` | varchar | Có | Stage hiện tại. |
| `stage_count` | integer | Không | Số stage của run. |
| `error_code` | varchar | Có | Mã lỗi. |
| `error_message` | text | Có | Nội dung lỗi. |
| `summary_json` | json | Không | Tóm tắt kết quả. |
| `created_at` | timestamptz | Không | Thời điểm bắt đầu. |
| `completed_at` | timestamptz | Có | Thời điểm hoàn tất. |

### `planning_run_stages`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã stage. |
| `run_id` | varchar | Không | Planning run sở hữu stage. |
| `sequence` | integer | Không | Thứ tự stage. |
| `stage` | varchar | Không | Tên stage. |
| `status` | varchar | Không | Trạng thái stage. |
| `duration_ms` | integer | Có | Thời lượng chạy. |
| `input_json` | json | Không | Input stage. |
| `output_json` | json | Không | Output stage. |
| `error_json` | json | Không | Lỗi stage. |
| `metadata_json` | json | Không | Metadata stage. |
| `created_at` | timestamptz | Không | Thời điểm tạo stage. |

## Bảng knowledge graph và nguồn dữ liệu

### `knowledge_entities`

Ngày sửa đổi cuối cùng: 2026-08-17.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã entity. |
| `canonical_name` | varchar | Không | Tên chuẩn. |
| `normalized_name` | varchar | Không | Tên đã chuẩn hóa. |
| `entity_type` | varchar | Không | Loại entity; gồm `Entertainment` cho các địa điểm giải trí/wellness được phân loại riêng bên cạnh `TravelPlace`. |
| `status` | varchar | Không | Trạng thái entity. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `review_count` | integer | Có | Tổng số review theo dữ liệu nguồn; không thay thế các row trong `reviews`. |

Ontology ứng dụng cho phép thêm `SubPlace` với cùng property contract như
`TravelPlace`: `id`, `name`, `type`, `latitude`, `longitude` là required và
toàn bộ metadata địa điểm còn lại là optional. SubPlace vẫn không phải itinerary
stop độc lập. Đây là type trong contract ứng dụng, không thêm cột hoặc table
mới. Batch curated v1 đã nạp năm node `pending` cho Hanoi
Old Quarter: Hàng Gai, Hàng Bạc, Hàng Mã, Lãn Ông và góc bia Tạ Hiện–Lương
Ngọc Quyến. Mỗi node giữ `latitude`, `longitude` và `address` là điểm đại diện
cho phố/giao điểm, có provenance và vẫn chờ verification. Batch hiệu chỉnh
`kg_curated_hanoi_old_quarter_subplace_activities_v2_20260821` giữ đúng một
`ActivityItem` cho mỗi SubPlace và đánh dấu batch v1 là `superseded_by_v2`.
Các batch giữ source trong property/relationship và staging import tương ứng;
không tự chuyển entity sang `verified`.

Migration `011_entertainment_node.sql` chỉ đổi `entity_type` từ `TravelPlace`
sang `Entertainment` cho nhóm tên đã được rà soát (spa, massage, billiard/billard,
bida, karaoke, gym, fitness hoặc nail). Migration không đổi `id`, không xoá
entity và không chạm vào `knowledge_relationships`, `knowledge_properties` hay
các bảng dữ liệu liên quan. Vì vậy các quan hệ hiện có tiếp tục trỏ tới cùng
node; truy vấn `travel place` lọc chính xác `TravelPlace`, còn hint
`entertainment`/`wellness` lọc `Entertainment`.

Migration `012_costume_entertainment_places.sql` tiếp tục phân loại các
`TravelPlace` chuyên cosplay/hóa trang thành `Entertainment`, dựa trên tên node
hoặc quan hệ `Offer_Item` tới `ActivityItem` tương ứng; migration cũng giữ
nguyên ID và các quan hệ hiện có.

Migration `013_outdoor_entertainment_places.sql` phân loại các địa điểm cung
cấp `Cắm trại` hoặc `Cưỡi ngựa` thành `Entertainment`. Các địa điểm gắn với
`Tham gia hoạt động mua bán địa phương` hoặc chợ không bị chuyển bởi migration
này và tiếp tục là `TravelPlace`.

### `knowledge_aliases`

Ngày sửa đổi cuối cùng: 2026-08-11.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã alias. |
| `entity_id` | varchar | Không | Entity sở hữu alias. |
| `alias` | varchar | Không | Tên thay thế. |
| `normalized_alias` | varchar | Không | Alias đã chuẩn hóa. |
| `language` | varchar | Không | Ngôn ngữ alias. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `alias_type` | varchar | Không | Loại alias. |
| `source` | text | Có | Nguồn alias. |
| `provider` | varchar | Có | Provider cung cấp alias. |
| `status` | varchar | Không | Trạng thái alias. |
| `confidence` | float8 | Có | Độ tin cậy alias. |
| `verified_at` | timestamptz | Có | Thời điểm xác minh. |

### `knowledge_properties`

Ngày sửa đổi cuối cùng: 2026-08-14.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã property. |
| `entity_id` | varchar | Không | Entity sở hữu property. |
| `key` | varchar | Không | Tên property. |
| `value` | text | Không | Giá trị property. |
| `source` | text | Có | Nguồn dữ liệu. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `note` | text | Có | Ghi chú property. |
| `fetch_at` | timestamptz | Có | Thời điểm dữ liệu property được lấy từ nguồn. |

Dữ liệu do Google Maps Playwright tạo giữ URL thật trong `source`, thời điểm
scrape trong `fetch_at`, và
`note=provider=google_maps_playwright;verification=not_verified`. Entity được
upsert với `status=pending`; admin đổi sang `verified` để cho phép trust như KG.
Entity `rejected` bị loại khỏi PlaceChecker. Adapter không lưu raw page payload.

### `knowledge_relationships`

Cập nhật lần cuối: 2026-08-13. Ontology runtime dùng `Special_Near`; `Must_Visit`
đã được đổi tên và các cạnh `Near` đã bị loại bỏ.

Ngày sửa đổi cuối cùng: 2026-08-11.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã relationship. |
| `from_entity_id` | varchar | Không | Entity nguồn. |
| `relationship_type` | varchar | Không | Loại quan hệ. |
| `to_entity_id` | varchar | Không | Entity đích. |
| `recommendations` | json | Có | Recommendation liên quan. |
| `source` | text | Có | Nguồn quan hệ. |
| `source_note` | text | Có | Ghi chú hoặc bằng chứng mô tả nguồn của quan hệ. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

Runtime relationship semantics observed on 2026-08-13:

- `Located_In`: place/ADM child → ADM parent;
- `Special_Experience`: ADM → `TravelPlace`, recommendations object may carry
  `status` and `match_type`;
- `Special_Near`: quan hệ gần giữa các place, gồm `TravelPlace` ↔ `TravelPlace`
  và `TravelPlace` ↔ `Restaurant`, với `distance_km`, `threshold_km` và optional
  derivation rule. PlaceChecker xử lý được cả hai hướng của cạnh;
- `Offer_Item`: place → item; recommendations may be an evidence array or an
  object containing status/priority;
- `Has_Style`: place/item → style. Runtime chỉ đọc `time_windows` và
  `time_duration` từ Style priority cao nhất có field tương ứng khi entity/item
  thiếu field đó. Property trực tiếp luôn thắng. HasStyle không tạo public tag,
  candidate, category, preference match hoặc quota.

Ontology contract bổ sung ngày 2026-08-21 khai báo `Has_Subplace` theo hướng
`TravelPlace` → `SubPlace`; đây là cạnh cấu trúc, không đánh dấu SubPlace là
special experience. `SubPlace` có thể dùng `Offer_Item` tới `ActivityItem`,
`FoodItem`, `DrinkItem` hoặc `ProductItem`. Pilot Hanoi Old Quarter hiện có năm
cạnh `Has_Subplace` và năm cạnh `Offer_Item`; mỗi SubPlace có đúng một target
`ActivityItem`. Mutation/importer runtime chưa dùng ma trận endpoint này để tự
động apply batch mới.

Batch `kg_curated_hoan_kiem_turtle_tower_subplace_v1_20260821` đã chuyển
`Turtle Tower` từ `TravelPlace` thành `SubPlace` của `Hoàn Kiếm Lake`, giữ
`latitude`/`longitude` hiện có và gắn một `ActivityItem` duy nhất.

Các item của pilot được chuẩn hóa thành node tái sử dụng (`lụa`, `bạc`, `bia
hơi`, `sightseeing`...). Quan hệ `Offer_Item.recommendations` giữ thêm
`action`/`displayTemplate` để lớp LLM sinh câu hiển thị theo place và item,
thay vì tạo một node dài cho từng câu.

Batch `kg_curated_top_hanoi_subplaces_v1_20260821` bổ sung 13 SubPlace có
tọa độ đại diện dưới Văn Miếu, Hoàng thành Thăng Long, Hỏa Lò, Trấn Quốc,
quần thể Hồ Chí Minh và Bảo tàng Dân tộc học; mỗi node có đúng một
`ActivityItem`.

Migration `019_curate_hanoi_subplaces.sql` chuyển 16 provider-backed
TravelPlace cấu thành thành SubPlace theo exact ID. Migration giữ properties,
aliases, images và quan hệ không cấu trúc; thay hai synthetic duplicate bằng
entity thật, tạo 14 item còn thiếu và reject hai provider duplicate chính xác.
Sau migration 019 có 33 SubPlace active; 33/33 có một parent `Has_Subplace`, ít
nhất một `Offer_Item` và tọa độ. Migration
`020_reparent_ba_dinh_subplaces.sql` chuyển Lăng Chủ tịch Hồ Chí Minh thành
SubPlace thứ 34, thêm `Offer_Item` cho Lăng và gom trực tiếp Lăng, Ao cá Bác Hồ,
Nhà sàn Bác Hồ dưới Ba Đình Square. Mô hình được làm phẳng để không có
`SubPlace -> SubPlace`.

Migration `021_curate_nearby_travelplace_subplaces.sql` audit các TravelPlace
gần nhau nhưng chỉ chuyển ba child có nguồn chính thức xác nhận containment:
Đại Trung Môn, Cổng làng Mông Phụ và Chợ gốm Bát Tràng. Sau migration có 37
SubPlace active, mỗi child mới có một `Has_Subplace`, một `Offer_Item`, tọa độ
và description có provenance. Bán kính gần nhau không tự tạo quan hệ; các điểm
độc lập và bản ghi nghi duplicate vẫn giữ nguyên để xử lý ở batch riêng.

Migration `022_complete_subplace_activity_items.sql` bổ sung đúng một
`ActivityItem` cho sáu SubPlace trước đó chỉ offer ProductItem, DrinkItem hoặc
FoodItem. Migration giữ nguyên các item cũ, tái sử dụng provenance hiện có và
đưa coverage nguồn note lên 37/37 SubPlace active có ít nhất một cạnh
`Offer_Item -> ActivityItem`.

Đợt chuẩn hóa dữ liệu cũng đã merge các bản ghi duplicate `Nhà Thờ Lớn Hà Nội`
và `WinMart`, giữ entity có nhiều review hơn, chuyển alias/quan hệ không trùng
sang entity giữ lại và loại quan hệ trùng.

Generic TravelPlace retrieval không chỉ đọc `Special_Experience`: nó còn lấy
`TravelPlace` nằm trong cây ADM qua `Located_In`, xen kẽ hai nhóm special và
non-special. Trong nhóm non-special, `Offer_Item -> ActivityItem`, metadata
đầy đủ và rating/review chỉ là tín hiệu xếp hạng; chúng không thay đổi ontology.
Read path đưa `entityType` và `time_windows` của target `ActivityItem` vào
relationship evidence để PlaceChecker phân biệt Offer Item activity và timing;
không thêm cột, table hoặc ghi ngược dữ liệu Knowledge Graph.

PlaceChecker nhận bốn place entity type từ catalog: `TravelPlace`, `Restaurant`,
`DrinkDessert` và `Entertainment` (ngoài `Accommodation`). Compact boundary
nhóm `DrinkDessert`/`Entertainment` vào pool optional `entertainment`; đây chỉ
là thay đổi read/projection contract, không thêm bảng hoặc cột.
PlaceChecker/Planner pipeline không duyệt `Has_Subplace`, không dùng child để
ranking candidate và không gửi child properties/items trong relationship
evidence. Vì vậy SubPlace không tham gia optimization hoặc routing. Read path riêng
`GET /v1/plans/places/subplaces?parentPlaceIds=` query trực tiếp cạnh
`Has_Subplace` và các property `address`, `latitude`, `longitude`, `image`,
`time_duration`, `price_min`, `rating`, `review_count` sau khi itinerary đã
render. Cùng query đó chỉ lấy `Offer_Item` có target active `ActivityItem` làm
ngữ cảnh cho structured Gemini sinh ghi chú ngắn. Public response đánh dấu
`noteSource="gemini"` và liệt kê `noteActivityItemIds`; context nội bộ
Offer/Activity không được serialize. Property `description` không còn được dùng
làm ghi chú. Thiếu ActivityItem hoặc Gemini lỗi thì note để trống, không dùng
fallback. Toàn bộ dữ liệu này chỉ phục vụ card/pin frontend và không được lưu
ngược vào planner output.
Named-place SQL search chung cả năm type theo canonical name, alias, address và
cây ADM, lấy top-1 trước khi cân nhắc Google Maps; query này không đọc
SpecialExperience/OfferItem/HasStyle. Runtime compact
pool dùng quota 12 TravelPlace, 6 Restaurant, 2 Entertainment và 3 DrinkDessert
mỗi ngày, cùng tối đa 3 Accommodation/toàn chuyến; chỉ Entertainment tự gợi ý
có Bayesian-adjusted rating từ 4,2/5 mới được giữ, đồng
thời tourist-suitability gate loại category cửa hàng/dịch vụ thương mại khỏi
optional pool. Entertainment phải có window giao từ 18:00; DrinkDessert dùng
window 07:00–18:00. Mỗi deficient entity type có một query catalog, không có
thematic fan-out hoặc external discovery. Chính sách này chỉ đọc các field
`rating`, `review_count` và time window hiện có nên không cần migration.
Runtime còn dùng canonical name/tag để sửa các leisure venue rõ ràng bị gắn
`TravelPlace` sai sang `Entertainment`, và chỉ tính popular TravelPlace khi có
ít nhất 500 review cùng Bayesian/popularity đủ cao. Đây là read-time policy;
không ghi sửa `knowledge_entities` và không cần migration.
Provider note hiện có cũng được đọc làm semantic context để nhận source category
thương mại như art supply store, photo booth, garden center và plant service;
không thêm cột và không ghi ngược category.

PlaceChecker metadata read path resolve property `tags` qua
`auto-attach/tags-auto.yml` tại runtime và chỉ chuyển canonical key hợp lệ.
Relationship evidence từ `Special_Experience`, `Offer_Item`, `Has_Style` và
`Special_Near` nằm ở field provenance riêng, không trở thành taxonomy group.
Scoring dùng các canonical tag này cho preference ratio, hard avoid và độ mới
`1 / (1 + số lần tag đã chọn)`; thay đổi là read-time policy, không thêm bảng
hoặc ghi ngược Knowledge Graph.

PlaceChecker food read path bắt đầu từ `FoodItem`/`DrinkItem` có
`Has_Style`, rồi reverse `Offer_Item` sang `Restaurant`/`DrinkDessert` trong cây
ADM và tính khoảng cách tới batch TravelPlace anchor, giới hạn 5 km.
`Special_Near` chỉ là evidence. Selector giữ provenance Style/Item, dùng target
mềm `2 × days` cho mỗi Style food/drink active và ưu tiên Item/quán chưa dùng
trong từng anchor region. Khi meal matching hoặc Style coverage còn thiếu, read
path chạy general ADM một lần. Item hiện có thể ở trạng thái `draft`; read path
chỉ loại entity `rejected`, thống nhất với policy catalog hiện tại. Không thêm
bảng/cột và không nối Item bằng tên.

Read path Style tổng quát ngày 2026-08-18 resolve tên request sang canonical
Style ID hoặc canonical Item ID trước. Từ Item, adapter theo `Has_Style` tới
Style rồi reverse `Offer_Item` sang holder trong cây ADM; holder chỉ gồm
`TravelPlace`, `Restaurant` và `DrinkDessert`. Với Style không có Item liên kết,
adapter dùng direct holder `Has_Style`. Selector dedup `place_id`, giữ provenance
Style/Item/relationship, dùng target `2 × days` cho từng Style active và trả
shortfall thay vì tạo dữ liệu giả. Đây là read/runtime state, không thêm bảng,
cột hoặc dữ liệu đếm vào Knowledge Graph.

### `knowledge_entity_images`

Ngày sửa đổi cuối cùng: 2026-08-11.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã ảnh. |
| `image_title` | varchar | Có | Tiêu đề ảnh. |
| `image_url` | text | Không | URL ảnh. |
| `entity_id` | varchar | Không | Entity sở hữu ảnh. |

### `source_documents`

Ngày sửa đổi cuối cùng: 2026-08-12. Bảng cache này hiện do module Explorer sở
hữu; migration là `backend/migrations/002_explorer_source_document_cache.sql`.
Adapter đọc tương thích artifact version 6/8, ghi version 9, dùng
TTL mặc định 7 ngày và unique canonical URL. Đây không phải bảng của
Information Finder.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã source document. |
| `canonical_url` | text | Không | URL chuẩn của nguồn. |
| `platform` | varchar | Không | Nền tảng nguồn. |
| `artifacts` | json | Không | Artifact đã thu thập. |
| `extracted_context` | json | Không | Context được trích xuất. |
| `artifact_hash` | varchar | Có | Hash artifact. |
| `extractor_version` | varchar | Có | Version extractor. |
| `fetched_at` | timestamptz | Không | Thời điểm lấy dữ liệu. |
| `created_at` | timestamptz | Không | Thời điểm tạo record. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `explorer_draft_cache`

Ngày sửa đổi cuối cùng: 2026-08-11. Bảng do Explorer sở hữu; migration là
`backend/migrations/003_explorer_draft_cache.sql`. Cache key bao gồm prompt,
evidence chuẩn hóa, model namespace và policy version.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `cache_key` | varchar | Không | SHA-256 của input synthesis chuẩn hóa. |
| `namespace` | varchar | Không | Version policy, provider và model. |
| `draft` | json | Không | `ExplorerDraft` đã tổng hợp. |
| `created_at` | timestamptz | Không | Thời điểm tạo record. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất và mốc TTL. |

### `reviews`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã review. |
| `author_name` | varchar | Có | Tên người viết. |
| `rating` | integer | Có | Điểm đánh giá. |
| `published_at` | timestamptz | Có | Thời điểm review được publish. |
| `when_text` | varchar | Có | Mô tả thời gian dạng text. |
| `language` | varchar | Có | Ngôn ngữ review. |
| `review_text` | text | Có | Nội dung review. |
| `created_at` | timestamptz | Không | Thời điểm lưu review. |
| `entity_id` | varchar | Không | Entity được review. |

### `festivals`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã lễ hội. |
| `source_id` | varchar | Không | Mã lễ hội từ nguồn. |
| `source_url` | varchar | Có | URL nguồn. |
| `name` | varchar | Không | Tên lễ hội. |
| `venue` | varchar | Có | Địa điểm tổ chức. |
| `scale_level` | varchar | Không | Quy mô lễ hội. |
| `timing` | varchar | Có | Thời gian tổ chức. |
| `province` | varchar | Có | Tỉnh/thành phố. |
| `district` | varchar | Có | Quận/huyện. |
| `deity` | text | Có | Đối tượng được thờ phụng. |
| `ceremony_part` | text | Có | Phần nghi lễ. |
| `festival_part` | text | Có | Phần hội. |
| `festival_type` | varchar | Có | Loại lễ hội. |
| `documentation` | text | Có | Tài liệu mô tả. |
| `protection_measure` | text | Có | Biện pháp bảo tồn. |
| `registration_time` | varchar | Có | Thời điểm đăng ký. |
| `recurrence` | varchar | Có | Chu kỳ lặp lại. |
| `listed_year` | integer | Có | Năm được ghi nhận. |
| `metadata` | json | Không | Metadata bổ sung. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `knowledge_graph_imports`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã import. |
| `source_label` | varchar | Không | Nhãn nguồn. |
| `source_url` | varchar | Có | URL nguồn. |
| `source_content` | text | Không | Nội dung nguồn. |
| `status` | varchar | Không | Trạng thái import. |
| `schema_version` | varchar | Không | Version schema. |
| `ontology_version` | varchar | Không | Version ontology. |
| `dataset_hash` | varchar | Không | Hash dataset. |
| `warnings` | json | Không | Cảnh báo import. |
| `node_count` | integer | Không | Số node. |
| `edge_count` | integer | Không | Số edge. |
| `issue_count` | integer | Không | Số issue. |
| `created_by` | bigint | Có | User tạo import. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `applied_at` | timestamptz | Có | Thời điểm áp dụng. |
| `applied_dataset_hash` | varchar | Có | Hash dataset đã áp dụng. |
| `error_message` | text | Có | Lỗi import. |
| `import_kind` | varchar | Không | Loại import. |
| `batch_id` | varchar | Có | Mã batch. |
| `source_document_id` | varchar | Có | Document nguồn. |
| `processing_status` | varchar | Không | Trạng thái xử lý. |
| `review_status` | varchar | Không | Trạng thái review. |
| `chat_id` | varchar | Có | Chat liên quan. |
| `destination` | varchar | Có | Điểm đến được suy ra. |
| `destination_entity_id` | varchar | Có | Entity điểm đến. |
| `candidate_reviews` | json | Không | Kết quả review candidate. |
| `source_type` | varchar | Không | Loại nguồn. |
| `source_name` | varchar | Có | Tên nguồn. |
| `image_mime_type` | varchar | Có | MIME type ảnh. |
| `image_data` | bytea | Có | Dữ liệu ảnh. |
| `force_refresh` | boolean | Không | Có bắt buộc lấy mới không. |
| `batch_position` | integer | Không | Vị trí trong batch. |
| `attempt_count` | integer | Không | Số lần thử. |
| `result_revision` | integer | Có | Revision kết quả. |
| `error_code` | varchar | Có | Mã lỗi. |
| `explorer_timing` | json | Có | Timing Explorer. |
| `planner_timing` | json | Có | Timing Planner. |
| `started_at` | timestamptz | Có | Thời điểm bắt đầu. |
| `finished_at` | timestamptz | Có | Thời điểm kết thúc. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `processing_phase` | varchar | Không | Phase xử lý hiện tại. |

### `knowledge_graph_import_nodes`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã node import. |
| `import_id` | varchar | Không | Import sở hữu node. |
| `temp_id` | varchar | Không | Mã tạm của node. |
| `entity_id` | varchar | Không | Entity liên quan. |
| `type` | varchar | Không | Loại node. |
| `canonical_name` | varchar | Không | Tên chuẩn. |
| `aliases` | json | Không | Danh sách alias. |
| `properties` | json | Không | Properties của node. |
| `evidence` | json | Không | Bằng chứng nguồn. |
| `confidence` | float8 | Không | Độ tin cậy. |
| `match_status` | varchar | Không | Trạng thái matching. |
| `match_candidates` | json | Không | Candidate matching. |
| `selected_entity_id` | varchar | Có | Entity được chọn. |
| `decision` | varchar | Không | Quyết định review. |
| `validation_issues` | json | Không | Issue validation. |
| `required_properties` | json | Không | Property bắt buộc. |
| `optional_properties` | json | Không | Property tùy chọn. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `source_document_id` | varchar | Có | Document nguồn. |
| `candidate_key` | varchar | Có | Khóa candidate. |
| `candidate_name` | varchar | Có | Tên candidate. |
| `search_region` | varchar | Có | Vùng tìm kiếm. |
| `source_evidence` | json | Không | Evidence chuẩn hóa. |
| `provider` | varchar | Có | Provider dữ liệu. |
| `provider_external_id` | varchar | Có | Mã ngoài provider. |
| `provider_snapshot` | json | Không | Snapshot từ provider. |
| `source_order` | integer | Có | Thứ tự trong nguồn. |
| `source_day` | integer | Có | Ngày trong nguồn. |
| `source_time_hint` | varchar | Có | Gợi ý thời gian. |
| `source_activity` | text | Có | Hoạt động từ nguồn. |
| `source_duration_minutes` | integer | Có | Thời lượng từ nguồn. |
| `preference_level` | varchar | Không | Mức độ ưu tiên. |
| `attributes` | json | Không | Thuộc tính bổ sung. |
| `reviewed_by` | bigint | Có | User review. |
| `reviewed_at` | timestamptz | Có | Thời điểm review. |
| `identity_status` | varchar | Không | Trạng thái định danh. |
| `selection_method` | varchar | Có | Cách chọn entity. |

### `knowledge_graph_import_edges`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã edge import. |
| `import_id` | varchar | Không | Import sở hữu edge. |
| `temp_id` | varchar | Không | Mã tạm của edge. |
| `from_ref` | varchar | Không | Node nguồn. |
| `relationship_type` | varchar | Không | Loại quan hệ. |
| `to_ref` | varchar | Không | Node đích. |
| `recommendations` | json | Không | Recommendation liên quan. |
| `source` | varchar | Không | Nguồn edge. |
| `evidence` | json | Không | Bằng chứng edge. |
| `confidence` | float8 | Không | Độ tin cậy. |
| `match_status` | varchar | Không | Trạng thái matching. |
| `decision` | varchar | Không | Quyết định review. |
| `validation_issues` | json | Không | Issue validation. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

## Bảng profile, social và preference

### `traveler_profiles`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `user_id` | integer | Không | User sở hữu profile. |
| `version` | integer | Không | Version profile. |
| `observation_count` | integer | Không | Số observation đã ghi nhận. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `traveler_preference_signals`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã preference signal. |
| `user_id` | integer | Không | User sở hữu signal. |
| `dimension` | varchar | Không | Chiều preference. |
| `value` | varchar | Không | Giá trị preference. |
| `label` | varchar | Không | Nhãn hiển thị. |
| `score` | float8 | Không | Điểm preference. |
| `confidence` | float8 | Không | Độ tin cậy. |
| `observations` | integer | Không | Số lần quan sát. |
| `position` | integer | Không | Vị trí xếp hạng. |
| `scope` | varchar | Không | Phạm vi preference. |
| `destination` | varchar | Không | Điểm đến áp dụng. |
| `origin` | varchar | Không | Nguồn phát sinh. |
| `status` | varchar | Không | Trạng thái signal. |
| `first_observed_at` | timestamptz | Không | Lần đầu quan sát. |
| `last_observed_at` | timestamptz | Không | Lần cuối quan sát. |
| `last_evidence_intake_id` | varchar | Có | Intake evidence gần nhất. |

### `traveler_preference_signal_sources`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `signal_id` | varchar | Không | Signal liên quan. |
| `source_type` | varchar | Không | Loại nguồn của signal. |

### `preference_observation_jobs`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã job. |
| `message_id` | varchar | Không | Message tạo job. |
| `user_id` | integer | Không | User liên quan. |
| `status` | varchar | Không | Trạng thái job. |
| `attempts` | integer | Không | Số lần thử. |
| `error_code` | varchar | Có | Mã lỗi. |
| `error_message` | text | Có | Nội dung lỗi. |
| `started_at` | timestamptz | Có | Thời điểm bắt đầu. |
| `completed_at` | timestamptz | Có | Thời điểm hoàn tất. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `user_posts`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã bài đăng. |
| `user_id` | integer | Không | User tạo bài. |
| `caption` | text | Không | Nội dung mô tả. |
| `media_url` | varchar | Không | URL media. |
| `location_name` | varchar | Không | Tên địa điểm. |
| `created_at` | timestamptz | Không | Thời điểm đăng. |
| `content_type` | varchar | Không | Loại nội dung. |

### `user_visited_places`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã record địa điểm đã đi. |
| `user_id` | integer | Không | User đã đi địa điểm. |
| `visited_at` | date | Không | Ngày ghé thăm. |
| `note` | text | Có | Ghi chú cá nhân. |
| `created_at` | timestamptz | Không | Thời điểm tạo record. |
| `entity_id` | varchar | Không | Entity địa điểm. |

### `travel_groups`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | integer | Không | Mã group. |
| `country_code` | varchar | Không | Mã quốc gia. |
| `country_name` | varchar | Không | Tên quốc gia. |
| `name` | varchar | Không | Tên group. |
| `photo_url` | varchar | Không | Ảnh group. |
| `visibility` | varchar | Không | Quyền hiển thị. |
| `created_at` | timestamptz | Không | Thời điểm tạo group. |

### `travel_group_memberships`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `group_id` | integer | Không | Group được tham gia. |
| `user_id` | integer | Không | User tham gia. |
| `joined_at` | timestamptz | Không | Thời điểm tham gia. |

### `travel_group_posts`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã bài đăng group. |
| `group_id` | integer | Không | Group chứa bài. |
| `author_id` | integer | Không | User viết bài. |
| `content` | text | Không | Nội dung bài. |
| `created_at` | timestamptz | Không | Thời điểm đăng. |

## Bảng Marketplace, order và payment

### `marketplace_plans`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã plan Marketplace. |
| `creator_id` | integer | Không | Creator sở hữu plan. |
| `status` | varchar | Không | Trạng thái plan. |
| `current_published_version_id` | varchar | Có | Version đang publish. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `marketplace_plan_versions`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã version. |
| `marketplace_plan_id` | varchar | Không | Plan cha. |
| `version` | integer | Không | Số version. |
| `source_plan_id` | varchar | Không | Plan nguồn. |
| `source_plan_version_id` | varchar | Không | Version plan nguồn. |
| `title` | varchar | Không | Tiêu đề plan. |
| `description` | text | Không | Mô tả plan. |
| `destination` | varchar | Không | Điểm đến. |
| `duration_days` | integer | Không | Số ngày. |
| `category` | varchar | Không | Danh mục. |
| `price_amount` | integer | Không | Giá bán. |
| `price_currency` | varchar | Không | Đơn vị tiền tệ. |
| `media_urls` | json | Không | Media preview. |
| `preview_snapshot` | json | Không | Snapshot preview. |
| `moderation_status` | varchar | Không | Trạng thái kiểm duyệt. |
| `rejection_reason` | text | Có | Lý do từ chối. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `published_at` | timestamptz | Có | Thời điểm publish. |

### `favorites`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `user_id` | integer | Không | User tạo favorite. |
| `marketplace_plan_id` | varchar | Không | Plan được yêu thích. |
| `created_at` | timestamptz | Không | Thời điểm favorite. |

### `orders`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã order. |
| `buyer_id` | integer | Không | User mua plan. |
| `total_amount` | integer | Không | Tổng tiền. |
| `currency` | varchar | Không | Đơn vị tiền tệ. |
| `status` | varchar | Không | Trạng thái order. |
| `idempotency_key` | varchar | Có | Khóa chống tạo trùng. |
| `provider_request_id` | varchar | Có | Mã request của provider. |
| `created_at` | timestamptz | Không | Thời điểm tạo order. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |
| `paid_at` | timestamptz | Có | Thời điểm thanh toán. |
| `refunded_at` | timestamptz | Có | Thời điểm hoàn tiền. |

### `order_items`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã order item. |
| `order_id` | varchar | Không | Order cha. |
| `marketplace_plan_id` | varchar | Không | Plan được mua. |
| `marketplace_plan_version_id` | varchar | Không | Version được mua. |
| `unit_amount` | integer | Không | Giá một đơn vị. |
| `currency` | varchar | Không | Đơn vị tiền tệ. |
| `quantity` | integer | Không | Số lượng. |

### `payments`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã payment. |
| `order_id` | varchar | Không | Order liên quan. |
| `provider` | varchar | Không | Payment provider. |
| `method` | varchar | Không | Phương thức thanh toán. |
| `request_id` | varchar | Có | Mã request thanh toán. |
| `transaction_id` | varchar | Có | Mã giao dịch. |
| `amount` | integer | Không | Số tiền. |
| `currency` | varchar | Không | Đơn vị tiền tệ. |
| `status` | varchar | Không | Trạng thái payment. |
| `payment_url` | text | Có | URL thanh toán. |
| `paid_at` | timestamptz | Có | Thời điểm trả tiền. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `payment_events`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã payment event. |
| `payment_id` | varchar | Có | Payment liên quan. |
| `order_id` | varchar | Có | Order liên quan. |
| `provider` | varchar | Không | Provider gửi event. |
| `provider_event_id` | varchar | Không | Mã event phía provider. |
| `request_id` | varchar | Có | Mã request liên quan. |
| `transaction_id` | varchar | Có | Mã giao dịch. |
| `event_type` | varchar | Không | Loại event. |
| `payload` | json | Không | Payload event. |
| `received_at` | timestamptz | Không | Thời điểm nhận event. |

### `entitlements`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã entitlement. |
| `user_id` | integer | Không | User được cấp quyền. |
| `order_id` | varchar | Không | Order tạo quyền. |
| `order_item_id` | varchar | Không | Item tạo quyền. |
| `marketplace_plan_id` | varchar | Không | Plan được cấp quyền. |
| `marketplace_plan_version_id` | varchar | Không | Version được cấp quyền. |
| `status` | varchar | Không | Trạng thái quyền. |
| `copied_plan_id` | varchar | Có | Plan cá nhân được copy. |
| `copied_plan_version_id` | varchar | Có | Version bản copy. |
| `created_at` | timestamptz | Không | Thời điểm cấp quyền. |
| `revoked_at` | timestamptz | Có | Thời điểm thu hồi. |

### `marketplace_reviews`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã review Marketplace. |
| `reviewer_id` | integer | Không | User viết review. |
| `marketplace_plan_id` | varchar | Không | Plan được review. |
| `marketplace_plan_version_id` | varchar | Có | Version được review. |
| `order_id` | varchar | Có | Order đủ điều kiện review. |
| `rating` | integer | Không | Điểm đánh giá. |
| `comment` | text | Không | Nội dung đánh giá. |
| `status` | varchar | Không | Trạng thái review. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `reports`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã report. |
| `reporter_id` | integer | Không | User gửi report. |
| `marketplace_plan_id` | varchar | Không | Plan bị report. |
| `marketplace_plan_version_id` | varchar | Có | Version bị report. |
| `reason` | varchar | Không | Lý do report. |
| `description` | text | Không | Mô tả chi tiết. |
| `status` | varchar | Không | Trạng thái xử lý. |
| `resolution` | text | Có | Kết quả xử lý. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `knowledge_auto_attach_rules`

Owned by the Knowledge Graph module and created by `backend/migrations/004_knowledge_auto_attach.sql`. The table persists admin-editable Style attachment rules, including keyword arrays, exclusions, exact names, default time windows, and the pending review status used for generated `Has_Style` candidates.

## Ghi chú quan trọng

Schema trên phản ánh database legacy đang tồn tại, không chứng minh rằng
backend mới đã hỗ trợ các nghiệp vụ tương ứng. Ngoại lệ được nhận ownership rõ
là `source_documents` của Explorer và các bảng tiền tố `information_finder_`;
các bảng còn lại không mặc nhiên là runtime contract của backend mới.
