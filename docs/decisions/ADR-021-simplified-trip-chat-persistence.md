# ADR-021: Persistence TripChat ba bảng và TripIntent snapshot

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

TripIntent trước đây được tách thành ba bảng quan hệ dù Explorer chỉ cần truyền
aggregate đã validate trực tiếp sang planning workflow. Conversation turn cũng
sao chép content và attachment sang message sau khi hoàn tất. Thiết kế này làm
runtime có cảm giác đi qua database và tăng số join mà không tạo thêm bất biến
nghiệp vụ cần thiết.

## Quyết định

TripChat dùng ba bảng nghiệp vụ:

- `trip_chats` giữ trạng thái hiện hành và `current_trip_intent` JSON đã validate;
- `trip_chat_messages` giữ cả message và lifecycle của user turn;
- `trip_revisions` giữ snapshot bất biến `trip_intent_payload + plan_payload`.

Explorer truyền `TripIntent` trực tiếp trong memory. Chỉ destination là trường
chặn planning; khi thiếu destination, hệ thống lưu draft vào `trip_chats` và hỏi
user. Các trường khác dùng default domain. Khi đủ destination, workflow chạy
`TripThemePlanner -> PlaceSelector -> OverallChecker` rồi mới ghi revision.

Migration backfill snapshot và lifecycle trước khi xóa
`trip_intent_versions`, `trip_intent_values`,
`trip_intent_destination_stays` và `trip_chat_turns`.

## Hệ quả

- Follow-up, audit và undo vẫn có snapshot chính xác.
- Không còn DB hand-off giữa Explorer và Planner.
- Turn API giữ `turnId` tương thích nhưng persistence nằm trên user message.
- TripIntent JSON chỉ được ghi sau Pydantic validation; truy vấn analytics sâu
  dùng JSON path/index khi có nhu cầu thực tế.
