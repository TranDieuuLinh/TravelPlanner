# ADR-018: TripIntent quan hệ có version là nguồn sự thật duy nhất

- Trạng thái: Đã thay thế bởi ADR-021
- Ngày: 2026-08-05

## Bối cảnh

Trip chat trước đây lưu toàn bộ Explorer context trong
`trip_chats.current_explorer` và lặp snapshot tại
`trip_chat_plan_revisions.explorer_payload`. Destination, ngày đi, nhóm đi,
ngân sách và constraint vì vậy chỉ tồn tại bên trong JSON, khó validate bằng DB,
khó truy vấn và dễ lệch contract khi Explorer thay đổi schema.

## Quyết định

Định nghĩa một aggregate `TripIntent` duy nhất gồm:

- `destination`;
- `timing`;
- `travelParty`;
- `budget`;
- `notes`;
- `preferences`;
- `constraints`.

Mỗi lần Explorer tạo hoặc sửa thành công sẽ ghi một record bất biến trong
`trip_intent_versions`. Scalar được lưu bằng cột typed. Danh sách và destination
stay được lưu ở `trip_intent_values` và `trip_intent_destination_stays`, không
dùng JSON. `trip_chats.current_trip_intent_id` trỏ tới version hiện hành;
`trip_chat_plan_revisions.trip_intent_id` ghi đúng version đã dùng để tạo plan.

Explorer public contract trả `tripIntent`. `PlanningIntent` và
`TripPlanningSpec` chỉ còn là projection typed phục vụ TripThemePlanner và
PlaceSelector. Follow-up luôn đọc TripIntent từ repository; không có fallback
sang snapshot Explorer cũ.

Candidate review không phải TripIntent. Nó được giữ theo `ExplorerIntake` để
retry resolution và bảo toàn provenance mà không trộn vào aggregate yêu cầu
chuyến đi.

Migration xóa ngay `trip_chats.current_explorer` và
`trip_chat_plan_revisions.explorer_payload`. Không backfill từ JSON cũ theo lựa
chọn sản phẩm; chat cũ không có TripIntent sẽ phải tạo một planning revision mới.

## Hệ quả

- Có thể validate, query và index các trường Where/When/Who/Budget trực tiếp.
- Mỗi plan revision truy vết được chính xác TripIntent version.
- Schema AI thay đổi không còn quyết định schema persistence.
- Migration mang tính phá tương thích và chủ động bỏ TripIntent JSON cũ.
- Danh sách typed cần thêm `kind` hoặc bảng con khi mở rộng domain.
