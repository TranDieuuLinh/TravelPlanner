# Database schema

Tài liệu này mô tả database mục tiêu cho VSF Travel dựa trên codebase hiện tại và
danh sách bảng chính đã chốt. Trạng thái hiện tại: codebase mới triển khai thật
bảng `users` qua SQLAlchemy/Alembic; các bảng còn lại là schema mục tiêu để thêm
migration và model trong các bước tiếp theo.

## Trạng thái triển khai

| Table | Status | Nguồn trong codebase |
| --- | --- | --- |
| `users` | Implemented | `backend/app/modules/users/model.py`, migration `20260727_0001_create_users_table.py` |
| `auth_sessions` | Implemented | `backend/app/modules/auth/model.py`, migration `20260727_0002_add_auth_and_profile.py` |
| `places` | Planned | Cần thêm module/model |
| `places` | Implemented | `backend/app/modules/places/model.py`, migration `20260727_0002_create_places_table.py` |
| `user_must_place` | Implemented | Candidate, attributes và dữ liệu resolve đầy đủ theo `intakeId`, migrations `20260728_0004` và `20260729_0007` |
| `place_external_refs` | Planned | Tham chiếu và độ mới dữ liệu từ place provider |
| `place_region_catalog_state` | Implemented | Trạng thái hiện tại theo khu vực, migration `20260727_0003` |
| `place_region_snapshots` | Implemented | Snapshot thống kê bất biến cho Planner, migration `20260727_0003` |
| `trips` | Planned | Liên quan module `plans` hiện đang dùng Pydantic/in-memory |
| `itinerary_items` | Planned | Nên dùng thay `trip_places` vì lưu được lịch trình chi tiết |
| `trip_members` | Planned | Cần cho chia sẻ trip |
| `marketplace_plans` | Implemented | Listing/sản phẩm ổn định của Marketplace, migration `20260727_0003_add_person_c_marketplace.py` |
| `marketplace_plan_versions` | Implemented | Snapshot bất biến của listing/version, migration `20260727_0003_add_person_c_marketplace.py` |
| `marketplace_plan_items` | Planned | Có thể thêm sau nếu cần lưu itinerary mẫu theo version |
| `orders` | Implemented | Đơn mua listing version, migration `20260727_0003_add_person_c_marketplace.py` |
| `order_items` | Implemented | Khóa marketplace plan version và giá mua, migration `20260727_0003_add_person_c_marketplace.py` |
| `payments` | Implemented | Giao dịch thanh toán của order, migration `20260727_0003_add_person_c_marketplace.py` |
| `payment_events` | Implemented | Event/IPN idempotent từ payment provider, migration `20260727_0003_add_person_c_marketplace.py` |
| `entitlements` | Implemented | Quyền truy cập sau thanh toán, migration `20260727_0003_add_person_c_marketplace.py` |
| `reviews` | Implemented | Review từ buyer cho marketplace plan, migration `20260727_0003_add_person_c_marketplace.py` |
| `reports` | Implemented | Báo cáo listing cho admin xử lý, migration `20260727_0003_add_person_c_marketplace.py` |
| `audit_events` | Implemented | Nhật ký hành động quan trọng, migration `20260727_0003_add_person_c_marketplace.py` |
| `favorites` | Implemented | User lưu marketplace plan yêu thích, migration `20260727_0003_add_person_c_marketplace.py` |
| `achievements` | Planned | Danh mục thành tựu |
| `user_achievements` | Planned | Tiến độ/thời điểm user đạt thành tựu |

## Core tables

### `users`

Lưu người dùng hệ thống.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Đã triển khai |
| `email` | varchar(255), unique | Đăng nhập/liên hệ |
| `full_name` | varchar(255) | Tên hiển thị |
| `role` | varchar(32) | `traveler`, `host`, `creator`, `admin` |
| `avatar_url` | varchar(500), nullable | Ảnh đại diện |
| `travel_preferences` | json | Profile có version: explicit preferences, aggregate scores, confidence, observation count và updatedAt |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `places`

Lưu địa điểm có thể xuất hiện trong lịch trình.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `name` | varchar | Tên địa điểm |
| `place_type` | varchar | attraction, restaurant, hotel, cafe, station, airport |
| `address` | text, nullable | Địa chỉ |
| `city` | varchar, nullable | Thành phố |
| `country` | varchar, nullable | Quốc gia |
| `country_code` | varchar(2), nullable | Mã quốc gia ISO, ví dụ `VN` |
| `region_key` | varchar(160), nullable | Khóa gom nhóm ổn định, ví dụ `vn,da-nang,hai-chau` |
| `primary_area` | varchar(160), nullable | Tên khu vực hiển thị |
| `latitude` | decimal, nullable | Tọa độ |
| `longitude` | decimal, nullable | Tọa độ |
| `status` | varchar(32) | `active`, `temporarily_closed`, `permanently_closed`, `unverified` |
| `opening_hours` | json, nullable | Giờ mở cửa đã chuẩn hóa |
| `typical_duration_minutes` | integer, nullable | Thời lượng ghé thăm điển hình |
| `data_confidence` | varchar(16) | `low`, `medium`, `high` |
| `source_fetched_at` | timestamptz, nullable | Thời điểm dữ liệu vận hành được lấy hoặc xác minh |
| `revision` | bigint | Tăng khi dữ liệu ảnh hưởng Planner thay đổi |
| `metadata` | json | Tags, mô tả ngắn và thuộc tính phụ không cần truy vấn thường xuyên |
| `deleted_at` | timestamptz, nullable | Soft delete để giữ toàn vẹn tham chiếu lịch trình |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

`city` và `country` vẫn được giữ để hiển thị và tương thích dữ liệu nhập, nhưng
không dùng làm khóa gom nhóm. Planner sử dụng `region_key`. Giờ mở cửa được đưa
ra khỏi `metadata`; ID của provider được lưu riêng trong `place_external_refs`.

### `user_must_place`

Lưu mọi candidate và dữ liệu resolve của intake theo chế độ không hỏi lại user.
Không có FK hoặc thao tác ghi sang `places`.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `intake_id` | varchar | Correlation ID trả cùng Explorer JSON |
| `user_id` | varchar, nullable | Khóa owner trả cùng response; Finder query cùng `intake_id` |
| `destination` | varchar | Điểm đến của intake |
| `candidate_key` | varchar | Khóa gộp trùng trong intake |
| `candidate_name` | varchar | Tên được trích xuất |
| `category` | varchar | Taxonomy mở rộng: food, cafe, attraction, nature, culture, shopping, nightlife, wellness, adventure, beach, family, hotel, transport, free_time, other |
| `attributes` | json | Tag chuẩn hóa như local, hidden_gem, photogenic, budget |
| `preference_level` | varchar | mentioned, preferred hoặc must_visit |
| `address_hint` | text, nullable | Gợi ý từ prompt/OCR/URL |
| `resolved_name` | varchar | Tên sau resolve |
| `address`, `city`, `country`, `country_code` | text/varchar, nullable | Địa chỉ chuẩn hóa khi tìm được |
| `primary_area` | varchar, nullable | Khu vực con |
| `latitude`, `longitude` | decimal, nullable | Tọa độ khi tìm được |
| `description` | text, nullable | Mô tả khi provider trả về |
| `provider`, `external_id` | varchar, nullable | Provenance của kết quả search |
| `sources` | json | Danh sách `{type, url?}` giữ provenance |
| `confidence` | decimal | 0 đến 1 |
| `notes` | text, nullable | Bằng chứng ngắn |
| `data_confidence` | varchar | low, medium, high |
| `fetched_at` | timestamptz, nullable | Độ mới dữ liệu |
| `attribution` | text, nullable | Attribution của provider |
| `resolution_status` | varchar | resolved, provisional, unresolved |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `place_external_refs`

Lưu định danh địa điểm theo provider mà không làm domain `Place` phụ thuộc vào
payload riêng của provider.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `place_id` | FK `places.id` | Địa điểm chuẩn hóa |
| `provider` | varchar(64) | Tên provider |
| `external_id` | varchar(255) | ID của địa điểm tại provider |
| `fetched_at` | timestamptz | Thời điểm lấy dữ liệu |
| `confidence` | varchar(16) | `low`, `medium`, `high` |
| `attributes` | json | Thuộc tính được phép lưu, không chứa payload thô |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `place_region_catalog_state`

Mỗi `region_key` có một dòng mutable để biết danh mục đã thay đổi và có cần tạo
snapshot mới hay không.

| Column | Type | Notes |
| --- | --- | --- |
| `region_key` | varchar(160) PK | Ví dụ `vn,da-nang,hai-chau` |
| `catalog_version` | bigint | Tăng khi Place trong khu vực thay đổi |
| `current_snapshot_id` | FK `place_region_snapshots.id`, nullable | Snapshot hiện tại Planner được phép dùng |
| `dirty_since` | timestamptz, nullable | Thời điểm bắt đầu có thay đổi chưa tổng hợp |
| `refresh_status` | varchar(16) | `clean`, `pending`, `running`, `failed` |
| `refresh_attempts` | integer | Số lần worker đã thử |
| `next_retry_at` | timestamptz, nullable | Thời điểm được retry |
| `last_error_code` | varchar(64), nullable | Mã lỗi an toàn, không lưu payload provider |
| `updated_at` | timestamptz | Cập nhật lúc |

### `place_region_snapshots`

Lưu snapshot thống kê bất biến mà Planner dùng để tạo `MacroPlan`. Snapshot mới
không ghi đè snapshot cũ; sau khi tính thành công,
`place_region_catalog_state.current_snapshot_id` mới được chuyển sang snapshot
mới.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `region_key` | varchar(160) | Khu vực được thống kê |
| `catalog_version` | bigint | Phiên bản danh mục Place nguồn |
| `algorithm_version` | varchar(32) | Version của logic thống kê |
| `source_fingerprint` | varchar(64) | Dấu vân tay dữ liệu Place thuộc khu vực và các vùng con |
| `place_count` | integer | Tổng Place hợp lệ |
| `active_place_count` | integer | Tổng Place đang hoạt động |
| `source_max_updated_at` | timestamptz, nullable | Mốc dữ liệu Place mới nhất được sử dụng |
| `metrics` | json | Thống kê theo loại, thời điểm, chất lượng và phân bố địa lý |
| `generated_at` | timestamptz | Thời điểm tạo snapshot |
| `expires_at` | timestamptz, nullable | Thời điểm nên làm mới |
| `created_at` | timestamptz | Tạo lúc |

`metrics` có thể chứa:

- số lượng theo `place_type` và `status`;
- `tagCounts`: số Place theo tag chuẩn hóa; một Place chỉ được tính một lần cho
  mỗi tag;
- `placeGroupCounts`: phân bố theo nhóm hoạt động cấp cao;
- `tagTimeCoverage`: độ phủ sáng, trưa, chiều và tối của từng tag;
- `tagDurationProfile`: thời lượng trung vị và cỡ mẫu theo tag;
- `indoorOutdoorMix`, `weatherSensitivityCounts` và
  `bookingRequirementCounts`;
- độ phủ hoạt động buổi sáng, trưa, chiều và tối;
- thời lượng điển hình theo loại địa điểm;
- số Place thiếu tọa độ, giờ mở cửa hoặc có dữ liệu cũ;
- tâm khu vực và bounding box;
- `areaProfiles`: hồ sơ các khu vực con nổi bật;
- `plannerSignals`: tag nổi trội, buổi mạnh/yếu, khu vực ứng viên và mức đa dạng
  hoạt động để Planner tạo `MacroPlan`/`DayBrief`.

Tag phải được chuẩn hóa và gộp alias trước khi đếm, ví dụ
`cafe, coffee_shop -> coffee` và `restaurant, food_drink -> food`. Một Place chỉ
được tính một lần cho mỗi tag chuẩn hóa. Tag không có dạng semantic như số điện
thoại hoặc chuỗi địa chỉ phải bị loại khỏi thống kê Planner.

Snapshot không lưu route chính xác giữa mọi cặp Place, giao thông hiện tại, thời
tiết, booking hoặc giá hiện tại. Finder và CheckOverall phải kiểm tra các dữ liệu
động này khi điền và kiểm tra plan.

### Luồng tự động thống kê Place

1. `PlaceCatalogService` thêm, sửa, đóng hoặc chuyển khu vực của Place và tăng
   `places.revision`; không chạy thống kê ngay.
2. Khi Planner yêu cầu một `region_key`, repository tính fingerprint từ các
   Place thuộc đúng khu vực đó và mọi `region_key` con.
3. Nếu fingerprint và `algorithm_version` trùng snapshot hiện tại, Planner dùng
   snapshot đó ngay.
4. Nếu dữ liệu hoặc thuật toán thay đổi, hệ thống tính lại, tạo một
   `place_region_snapshots` bất biến mới và tăng `catalog_version`.
5. `place_region_catalog_state.current_snapshot_id` được chuyển sang snapshot
   mới; snapshot cũ vẫn được giữ để truy vết.

Thay đổi ở khu vực khác không làm snapshot đang được Planner yêu cầu hết hạn.
Nếu refresh thất bại, snapshot cũ không bị ghi đè.

### `trips`

Lưu chuyến đi cá nhân do user tạo.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `owner_id` | FK `users.id` | Chủ trip |
| `title` | varchar | Tên trip |
| `destination` | varchar | Điểm đến chính |
| `start_date` | date, nullable | Ngày bắt đầu |
| `end_date` | date, nullable | Ngày kết thúc |
| `budget_amount` | integer, nullable | Số tiền theo đơn vị nhỏ nhất |
| `budget_currency` | varchar(3), nullable | ISO currency, ví dụ `VND` |
| `party_size` | integer | Số người |
| `status` | varchar | draft, generating, ready, archived |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plans`

Lưu listing/sản phẩm ổn định do creator đóng gói và bán. Nội dung hiển thị,
preview, giá và liên kết tới plan version của Planner nằm trong
`marketplace_plan_versions` để version đã publish hoặc đã bán không bị thay đổi.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `creator_id` | FK `users.id` | Người bán |
| `status` | varchar | draft, published, unpublished, retired |
| `current_published_version_id` | varchar, nullable | Version public hiện tại; service bảo vệ vì không tạo FK vòng |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plan_versions`

Snapshot bất biến của một listing. Đây là bảng quan trọng nhất cho Người C vì
checkout, entitlement và copy plan phải khóa đúng version đã mua.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing cha |
| `version` | integer | Số version theo từng listing |
| `source_plan_id` | varchar | Plan gốc do Planner quản lý; opaque vì Planner chưa có persistence |
| `source_plan_version_id` | varchar | Version plan gốc được publish |
| `title` | varchar | Tên listing/version |
| `description` | text | Nội dung mô tả public |
| `destination` | varchar | Điểm đến |
| `duration_days` | integer | Số ngày |
| `category` | varchar | Nhóm tìm kiếm/hiển thị |
| `price_amount` | integer | Giá theo đơn vị nhỏ nhất |
| `price_currency` | varchar(3) | ISO currency, mặc định `VND` |
| `media_urls` | json | URL ảnh/video public cho listing |
| `preview_snapshot` | json | Preview an toàn từ Planner tại thời điểm tạo version |
| `moderation_status` | varchar | draft, pending_review, approved, rejected, published |
| `rejection_reason` | text, nullable | Lý do admin từ chối |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |
| `published_at` | timestamptz, nullable | Thời điểm publish |

### `orders`

Lưu đơn mua plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `buyer_id` | FK `users.id` | Người mua |
| `total_amount` | integer | Tổng tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, paid, fulfilled, cancelled, refunded |
| `idempotency_key` | varchar, unique, nullable | Chống tạo checkout trùng |
| `provider_request_id` | varchar, unique, nullable | Request ID gửi tới provider thanh toán |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |
| `paid_at` | timestamptz, nullable | Thời điểm order được xác nhận paid |
| `refunded_at` | timestamptz, nullable | Thời điểm refund được xác nhận |

### `payments`

Lưu giao dịch thanh toán của order.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order được thanh toán |
| `provider` | varchar | Stripe, VNPay, Momo, manual |
| `method` | varchar | card, wallet, bank_transfer |
| `request_id` | varchar, unique, nullable | Request ID phía provider |
| `transaction_id` | varchar, unique | Mã giao dịch provider |
| `amount` | integer | Số tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, succeeded, failed, refunded |
| `payment_url` | text, nullable | URL redirect thanh toán sandbox/production |
| `paid_at` | timestamptz, nullable | Thời điểm thanh toán thành công |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `payment_events`

Lưu event/IPN từ provider để xử lý idempotent và phục vụ đối soát.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `payment_id` | FK `payments.id`, nullable | Payment liên quan nếu đã match được |
| `order_id` | FK `orders.id`, nullable | Order liên quan nếu đã match được |
| `provider` | varchar | momo, stripe, vnpay, manual |
| `provider_event_id` | varchar | Mã event hoặc khóa idempotency từ provider |
| `request_id` | varchar, nullable | Request ID trong payload |
| `transaction_id` | varchar, nullable | Transaction ID trong payload |
| `event_type` | varchar | Loại event |
| `payload` | json | Payload đã được kiểm tra và được phép lưu |
| `received_at` | timestamptz | Thời điểm nhận event |

### `reviews`

Review của buyer cho marketplace plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `reviewer_id` | FK `users.id` | Buyer viết review |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được review |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id`, nullable | Version được review |
| `order_id` | FK `orders.id`, nullable | Order chứng minh quyền review |
| `rating` | integer | 1 đến 5 |
| `comment` | text | Nội dung review |
| `status` | varchar | published, hidden, flagged |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `entitlements`

Quyền truy cập được cấp sau khi order/payment hợp lệ. Refund thu hồi entitlement
nhưng không xóa bản plan buyer đã copy.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `user_id` | FK `users.id` | Buyer sở hữu quyền |
| `order_id` | FK `orders.id` | Order cấp quyền |
| `order_item_id` | FK `order_items.id`, unique | Mỗi order item cấp tối đa một entitlement |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing đã mua |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id` | Version đã mua |
| `status` | varchar | active, revoked, refunded |
| `copied_plan_id` | varchar, nullable | Plan copy do Planner tạo cho buyer |
| `copied_plan_version_id` | varchar, nullable | Version copy của buyer |
| `created_at` | timestamptz | Tạo lúc |
| `revoked_at` | timestamptz, nullable | Thời điểm thu hồi quyền |

### `reports`

Nội dung user báo cáo để admin xử lý.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `reporter_id` | FK `users.id` | Người báo cáo |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing bị báo cáo |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id`, nullable | Version bị báo cáo |
| `reason` | varchar | Lý do báo cáo |
| `description` | text | Mô tả chi tiết |
| `status` | varchar | pending, reviewed, dismissed, resolved |
| `resolution` | text, nullable | Kết quả xử lý |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `audit_events`

Nhật ký hành động quan trọng như publish, payment, refund và admin review.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `actor_id` | FK `users.id`, nullable | User thực hiện hành động |
| `action` | varchar | Tên hành động |
| `resource_type` | varchar | Loại tài nguyên |
| `resource_id` | varchar, nullable | ID tài nguyên |
| `request_id` | varchar, nullable | Request ID để truy vết |
| `metadata` | json | Metadata an toàn, không chứa secret/token |
| `created_at` | timestamptz | Tạo lúc |

### `achievements`

Danh mục thành tựu/huy hiệu.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `code` | varchar, unique | Mã máy ổn định |
| `name` | varchar | Tên hiển thị |
| `description` | text | Mô tả |
| `badge_icon_url` | varchar, nullable | Icon huy hiệu |
| `criteria` | json | Điều kiện đạt được |
| `created_at` | timestamptz | Tạo lúc |

## Link tables

### `itinerary_items`

Liên kết `trips` với `places`, đồng thời lưu chi tiết lịch trình. Nên dùng bảng
này thay cho `trip_places` vì nó không chỉ nói "trip có place", mà còn mô tả
place nằm ở ngày nào, giờ nào, thứ tự nào.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `trip_id` | FK `trips.id` | Trip sở hữu item |
| `place_id` | FK `places.id`, nullable | Có thể null cho free-text item |
| `day_number` | integer | Ngày thứ mấy trong trip |
| `start_time` | time, nullable | Giờ bắt đầu local |
| `end_time` | time, nullable | Giờ kết thúc local |
| `sort_order` | integer | Thứ tự trong ngày |
| `cost_amount` | integer, nullable | Chi phí dự kiến |
| `cost_currency` | varchar(3), nullable | ISO currency |
| `notes` | text, nullable | Ghi chú |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plan_items`

Lưu itinerary mẫu của plan được bán.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan bán |
| `place_id` | FK `places.id`, nullable | Địa điểm trong mẫu |
| `day_number` | integer | Ngày thứ mấy |
| `start_time` | time, nullable | Giờ bắt đầu |
| `end_time` | time, nullable | Giờ kết thúc |
| `sort_order` | integer | Thứ tự trong ngày |
| `notes` | text, nullable | Ghi chú creator |

### `trip_members`

Liên kết user với trip.

| Column | Type | Notes |
| --- | --- | --- |
| `trip_id` | FK `trips.id` | Composite key |
| `user_id` | FK `users.id` | Composite key |
| `role` | varchar | owner, editor, viewer |
| `joined_at` | timestamptz | Thời điểm tham gia |

### `user_achievements`

Liên kết user với achievement.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | FK `users.id` | Composite key |
| `achievement_id` | FK `achievements.id` | Composite key |
| `progress` | integer | Tiến độ hiện tại |
| `achieved_at` | timestamptz, nullable | Thời điểm đạt được |

### `order_items`

Liên kết order với marketplace plan version đã mua. Đây là nơi khóa giá và
version tại thời điểm checkout.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được mua |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id` | Version được mua |
| `unit_amount` | integer | Giá tại thời điểm mua |
| `currency` | varchar(3) | ISO currency |
| `quantity` | integer | Mặc định 1 |

### `favorites`

User lưu marketplace plan yêu thích.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | FK `users.id` | Composite key |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Composite key |
| `created_at` | timestamptz | Tạo lúc |

## Quan hệ chính

```text
users 1--N trips
users N--N trips through trip_members
trips 1--N itinerary_items
places 1--N itinerary_items
places 1--N place_external_refs
place_region_catalog_state 1--N place_region_snapshots
place_region_catalog_state 0--1 current place_region_snapshots

users 1--N marketplace_plans
marketplace_plans 1--N marketplace_plan_versions
marketplace_plans 1--N marketplace_plan_items (planned)
places 1--N marketplace_plan_items (planned)

users 1--N orders
orders 1--N order_items
marketplace_plans 1--N order_items
marketplace_plan_versions 1--N order_items
orders 1--N payments
orders 1--N payment_events
orders 1--N entitlements

users 1--N reviews
marketplace_plans 1--N reviews
marketplace_plan_versions 1--N reviews
users N--N marketplace_plans through favorites
users 1--N reports
users 1--N audit_events

users N--N achievements through user_achievements
```

## Index và constraint nên có

- `users.email` unique.
- `places`: index `region_key, status`; index `region_key, place_type, status`;
  index `source_fetched_at`; và nếu dùng Postgres thì cân nhắc geo index cho tọa
  độ.
- `place_external_refs`: unique `provider, external_id`; index `place_id`.
- `place_region_snapshots`: unique
  `region_key, catalog_version, algorithm_version`; index
  `region_key, generated_at`.
- `place_region_catalog_state.current_snapshot_id` phải tham chiếu snapshot có
  cùng `region_key`; bất biến này được bảo vệ trong service/transaction.
- `trips.owner_id`, `itinerary_items.trip_id`, `itinerary_items.place_id`.
- `itinerary_items`: unique mềm trên `trip_id, day_number, sort_order`.
- `trip_members`: primary key `trip_id, user_id`.
- `marketplace_plans.creator_id`, `marketplace_plans.status`,
  `marketplace_plans.current_published_version_id`.
- `marketplace_plan_versions`: unique `marketplace_plan_id, version`; index
  category, destination, price, moderation status, `source_plan_id` và
  `source_plan_version_id`.
- `marketplace_plan_items`: planned; nếu triển khai nên unique mềm trên
  `marketplace_plan_version_id, day_number, sort_order`.
- `orders.buyer_id`, `orders.status`.
- `order_items.order_id`, `order_items.marketplace_plan_id`,
  `order_items.marketplace_plan_version_id`.
- `payments.order_id`, `payments.request_id` unique,
  `payments.transaction_id` unique.
- `payment_events`: unique `provider, provider_event_id`; index `order_id`,
  `request_id`, `transaction_id`.
- `entitlements.order_item_id` unique; index user, order, status và version.
- `reviews`: unique `reviewer_id, marketplace_plan_id`.
- `reports`: index reporter, reason và status.
- `audit_events`: index actor, action, resource và request ID.
- `favorites`: primary key `user_id, marketplace_plan_id`.
- `achievements.code` unique.
- `user_achievements`: primary key `user_id, achievement_id`.

## Migration plan đề xuất

1. Thêm `places` và `place_external_refs`.
2. Thêm `place_region_catalog_state`, `place_region_snapshots` và background job
   cập nhật thống kê khu vực.
3. Thêm `trips`, `trip_members`, `itinerary_items`.
4. Chuyển module `plans` từ in-memory repository sang SQLAlchemy repository và
   lưu snapshot Place đã dùng trong lần lập plan.
5. Đã thêm cụm Người C trong migration `20260727_0003`: `marketplace_plans`,
   `marketplace_plan_versions`, `favorites`, `orders`, `order_items`,
   `payments`, `payment_events`, `entitlements`, `reviews`, `reports` và
   `audit_events`.
6. Nếu cần query itinerary mẫu bằng SQL, thêm `marketplace_plan_items` theo
   `marketplace_plan_versions`, không theo listing gốc.
7. Thêm `achievements`, `user_achievements`.

Trong code hiện tại, bước 4 là điểm chuyển quan trọng nhất: `PlanRepository` đang
lưu trong memory, vì vậy dữ liệu plan sẽ mất khi backend restart.

## Công cụ thống kê Place hiện tại

Module `backend/app/modules/places/auto_statistics` dùng
`SqlAlchemyPlaceRepository` để đọc `places` từ PostgreSQL. Import CSV chỉ nằm ở
script biên `backend/scripts/import_places_to_postgres.py`, không phải repository
runtime. Create/update Place qua `PlaceCatalogService` chỉ tăng `revision` và
commit. Khi Planner yêu cầu một `region_key`, `auto_statistics` kiểm tra
fingerprint của đúng khu vực đó và các vùng con:

- fingerprint không đổi: đọc snapshot hiện tại từ
  `place_region_snapshots`;
- fingerprint thay đổi: tạo snapshot bất biến mới, tăng `catalog_version` và
  chuyển `place_region_catalog_state.current_snapshot_id`;
- thay đổi ở khu vực khác không làm snapshot đang được yêu cầu hết hạn.

Planner workflow đã gọi trực tiếp `get_for_planner(region_key)`. Contract nhận
`regionKey` chuẩn hóa; để tương thích request cũ, backend có thể chuẩn hóa
destination Việt Nam, ví dụ `Hà Nội` thành `vn,ha-noi`. Snapshot ID và version
được giữ trong internal trace/log của Planner, không đưa vào `MacroPlan` hoặc
Finder context. Thay đổi này không thêm hoặc xóa cột database.
