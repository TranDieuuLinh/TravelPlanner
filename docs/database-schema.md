# Database schema thực tế

Cập nhật lần cuối: 2026-08-11.

## Phạm vi và trạng thái

Tài liệu này được lấy trực tiếp từ database `travelplanner` trong container
PostgreSQL `pgvector/pgvector:0.8.2-pg16` đang chạy qua Docker Compose.

Database hiện có schema legacy với 31 table. Backend LangGraph mới trong
`backend/src/app` không có SQLAlchemy model để đọc các table legacy. Information
Finder có repository `asyncpg` và migration SQL riêng, chỉ sở hữu các bảng tiền
tố `information_finder_`. Vì vậy cần phân biệt:

- **Database runtime:** các table được liệt kê bên dưới vẫn tồn tại trong
  PostgreSQL volume.
- **Backend mới:** không sử dụng các table legacy; graph state vẫn dùng
  `InMemorySaver`. Information Finder sẽ dùng các bảng cache mô tả bên dưới khi
  có `DATABASE_URL` và migration đã được áp dụng.

`shared/tools/search_places/` hiện chỉ định nghĩa provider port và engine
xếp hạng/policy. Thay đổi này không thêm migration, không đọc trực tiếp các bảng
Knowledge Graph legacy và chưa nối PostgreSQL runtime. Adapter Knowledge Graph
tương lai phải nhận ownership/database đích rõ ràng trước khi query entity,
alias, property và quan hệ ADM; external adapter chỉ được trả payload đã chuẩn
hóa qua contract.

## Schema cache nguồn Information Finder

Migration nguồn: `backend/migrations/001_information_finder_source_cache.sql`.
Migration chưa được tự động áp vào volume đang tồn tại trong lần cập nhật tài
liệu này. Docker áp migration khi khởi tạo volume mới; với volume hiện hữu cần
chạy migration thủ công và kiểm tra backup trước.

| Bảng | Trách nhiệm chính |
|---|---|
| `information_finder_source_documents` | Canonical URL duy nhất, domain, title, provider và `review_status` mặc định `pending`. |
| `information_finder_source_snapshots` | Nội dung theo content hash; phân biệt `published_at`, `source_updated_at`, `last_fetched_at`, `expires_at` và provenance Tavily. |
| `information_finder_source_chunks` | Chunk khoảng 300 token, overlap khoảng 50 token và generated `tsvector`. |
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

Ngày sửa đổi cuối cùng: 2026-08-10.

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

### `auth_sessions`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | integer | Không | Khóa chính session. |
| `user_id` | integer | Không | User sở hữu session. |
| `jti` | varchar | Không | Mã định danh refresh token. |
| `refresh_token_hash` | varchar | Không | Hash của refresh token. |
| `expires_at` | timestamptz | Không | Thời điểm session hết hạn. |
| `revoked_at` | timestamptz | Có | Thời điểm session bị thu hồi. |
| `replaced_by_jti` | varchar | Có | JTI của session thay thế. |
| `created_at` | timestamptz | Không | Thời điểm tạo session. |
| `last_used_at` | timestamptz | Có | Lần cuối session được dùng. |

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

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | varchar | Không | Mã entity. |
| `canonical_name` | varchar | Không | Tên chuẩn. |
| `normalized_name` | varchar | Không | Tên đã chuẩn hóa. |
| `entity_type` | varchar | Không | Loại entity. |
| `status` | varchar | Không | Trạng thái entity. |
| `created_at` | timestamptz | Không | Thời điểm tạo. |
| `updated_at` | timestamptz | Không | Lần cập nhật gần nhất. |

### `knowledge_aliases`

Ngày sửa đổi cuối cùng: 2026-08-10.

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

Ngày sửa đổi cuối cùng: 2026-08-11.

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

### `knowledge_relationships`

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

### `knowledge_entity_images`

Ngày sửa đổi cuối cùng: 2026-08-10.

| Cột | Kiểu | Nullable | Giải thích |
|---|---|---|---|
| `id` | bigint | Không | Mã ảnh. |
| `image_title` | varchar | Có | Tiêu đề ảnh. |
| `image_url` | text | Không | URL ảnh. |
| `entity_id` | varchar | Không | Entity sở hữu ảnh. |

### `source_documents`

Ngày sửa đổi cuối cùng: 2026-08-10.

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

## Ghi chú quan trọng

Schema trên phản ánh database legacy đang tồn tại, không chứng minh rằng
backend mới đã hỗ trợ các nghiệp vụ tương ứng. Đặc biệt, backend mới hiện
chưa kết nối tới PostgreSQL và container `backend` cần được kiểm tra riêng vì
đang ở trạng thái restart loop.
