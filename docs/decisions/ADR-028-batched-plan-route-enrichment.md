# ADR-028: Batch route theo ngày và transit theo preference

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-06
- Thay thế một phần ADR-008 cho route enrichment khi tạo plan

## Bối cảnh

Global itinerary optimizer đã dùng `sources_to_targets` để gom activity giữa
các ngày, nhưng route enrichment sau cùng vẫn gọi `pedestrian`, `auto` và
OpenTripPlanner tuần tự cho từng cặp stop. Một plan ba ngày có 19 item và 16 leg
đã tạo 34 request Valhalla cùng một request OTP, khiến PlaceSelector mất khoảng
38 giây dù allocation deterministic đã hoàn tất.

Route chi tiết chỉ cần sau khi allocation, meal anchor và thứ tự item đã chốt.
Public transit còn phụ thuộc ngày/giờ và không cần nằm trong critical path khi
user không ưu tiên hoặc bắt buộc mode này.

## Quyết định

- Giữ global travel-time matrix hiện hành để gom activity và cân bằng duration
  giữa các ngày. Relevance, hard constraint, `sourceDay`, giờ mở cửa và capacity
  vẫn đứng trước route cost.
- Nearby graph survey lọc Haversine trước, sau đó lấy chi phí từ một
  `sources_to_targets` matrix cho anchor và toàn bộ shortlist. Runtime không
  fallback sang N request point-to-point khi matrix lỗi; khi đó dùng Haversine.
- Valhalla road adapter hỗ trợ `calculate_many`: một ordered day được gửi bằng
  một request `/route`, response được tách thành `RouteCalculation` riêng cho
  từng adjacent leg và cache lại theo cặp.
- Trước pedestrian batch, dùng Haversine miễn phí làm prefilter 2.000 m. Route
  pedestrian provider-backed không quá 1.500 m được chọn làm leg chính; leg còn
  lại dùng auto khi mode này không bị tránh.
- Auto batch chỉ chạy khi có ít nhất một leg không có walking route thực dụng,
  hoặc user ưu tiên car. Vì request batch chứa cả ordered day, kết quả auto của
  leg ngắn có thể được giữ làm alternative mà không phát sinh thêm request.
- OpenTripPlanner chỉ nằm trong critical path khi user ưu tiên bus/train/transit,
  tránh car mà walking không thực dụng, hoặc toàn bộ road route không có kết quả.
  Hard constraint tránh car không được âm thầm đổi thành ride-hailing.
- Batch road failure không làm hỏng plan; từng leg vẫn có thể dùng
  `geodesic_estimate`, `verified=false`. Public transit không có itinerary cùng
  geometry thật thì không được tạo estimate.
- API chỉ đường tương tác và mutation yêu cầu một mode cụ thể tiếp tục dùng
  point-to-point route để trả lựa chọn theo thao tác của user; ADR này chỉ đổi
  critical path tạo/revise plan.
- Response Planner đầu tiên giữ global route matrix trong critical path nhưng
  chỉ gắn leg `geodesic_estimate`, `routeEnrichmentStatus=pending`. Client gọi
  endpoint enrichment riêng sau khi đã render plan. Endpoint dùng optimistic
  revision, thay coarse leg bằng detailed route, fit lại timeline, chạy lại
  Checker và lưu revision kế tiếp; vì vậy enrichment không thể ghi đè một edit
  mới hơn của user.

## Hệ quả

- Plan mặc định giảm từ tối đa hai Valhalla request mỗi leg xuống tối đa hai
  Valhalla request mỗi ngày; ngày toàn walking hoặc user ưu tiên car chỉ cần một.
- Thời gian detailed route không còn chặn response plan đầu tiên. UI vẫn phải
  mô tả plan là đang hoàn thiện route cho tới khi status là `completed`.
- Plan không còn tự gọi OTP chỉ để tạo alternative khi user không có transit
  preference. UI có thể yêu cầu chỉ đường/transit riêng sau khi plan đã hiển thị.
- Valhalla multi-location dùng departure time của leg đầu làm context road cho
  cả batch. ETA không được mô tả là traffic realtime.
- Cần giữ test cho số batch call, ánh xạ đúng số leg, Haversine prefilter,
  preference/avoid mode và fallback khi provider lỗi.
