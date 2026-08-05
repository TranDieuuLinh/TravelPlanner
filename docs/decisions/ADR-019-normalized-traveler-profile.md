# ADR-019: Traveler Profile quan hệ, có provenance và quyền kiểm soát

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

Preference learning đã tồn tại nhưng lưu aggregate trong
`users.travel_preferences` dạng JSON. Cách này khó query, khó quản lý từng
signal và không thể hiện rõ provenance hoặc quyền xóa profile độc lập.

## Quyết định

1. Tách Traveler Profile dài hạn khỏi TripIntent của từng chuyến.
2. Dùng ba bảng quan hệ: `traveler_profiles`,
   `traveler_preference_signals` và `traveler_preference_signal_sources`.
3. Mỗi signal lưu dimension/value, score, confidence, observation count,
   explicit/inferred, trạng thái, thời gian quan sát và Explorer intake gần nhất.
4. Chỉ signal đủ confidence mới được lưu; signal suy luận cần ít nhất hai lần
   quan sát trước khi ảnh hưởng Planner. Preference user xác nhận có hiệu lực
   ngay.
5. Không suy luận/lưu trait nhạy cảm. Không lưu raw prompt, transcript hay OCR
   trong profile.
6. TripIntent hiện tại luôn override Traveler Profile. User có API xem, sửa
   preference explicit và xóa toàn bộ profile.
7. Migration backfill dữ liệu JSON cũ rồi xóa cột `users.travel_preferences`;
   không duy trì hai nguồn dữ liệu hoặc fallback JSON.

## Hệ quả

- Explorer và Planner đọc một nguồn profile trong database, query được từng
  signal và provenance.
- Schema nhiều bảng hơn nhưng quyền riêng tư, audit và khả năng hiệu chỉnh rõ
  ràng hơn.
- Các signal từ một nội dung tham khảo đơn lẻ chưa lập tức trở thành sở thích
  lâu dài có hiệu lực.
