# ADR-008: Routing tự vận hành với Valhalla và OpenTripPlanner

- Trạng thái: Được thay thế một phần bởi ADR-028 cho route enrichment của plan
- Ngày: 2026-07-31
- Thay thế phần quyết định provider trong ADR-002

## Bối cảnh

Planner cần route ô tô, đi bộ, matrix và public transit mà không phụ thuộc API
key hoặc quota thương mại theo request. Hệ thống đã có interface
`RouteProvider`, `TravelTimeMatrixProvider` và `TransitRouteProvider`, nên có
thể thay adapter mà không đổi contract domain.

## Quyết định

- Dùng Valhalla tự vận hành cho route `pedestrian`/`auto` và
  `sources_to_targets`.
- Luồng `/day-directions` giữ nguyên thứ tự itinerary; không gọi matrix hoặc
  shortest-path optimizer. Valhalla/OTP chỉ tính mode và route cho từng leg theo
  thứ tự đã lưu.
- Luồng chỉ đường tương tác vẫn có thể lấy cả route `pedestrian` và `auto` cho
  từng leg. Route enrichment khi tạo plan được ADR-028 thay bằng batch theo ngày,
  Haversine prefilter và transit theo preference để tránh fan-out provider.
- Dùng OpenTripPlanner GTFS GraphQL API cho public transit theo lịch.
- Place resolution dùng catalog nội bộ rồi Google Maps Playwright; Valhalla và
  OTP không phải POI geocoder.
- Không dùng API key cho Valhalla hoặc OTP trong cấu hình self-host.
- Chuẩn hóa provenance thành `valhalla_routing`, `valhalla_matrix` và
  `opentripplanner_transit`.
- Giữ fallback `geodesic_estimate`, `verified=false` khi road provider không
  sẵn sàng. Không tạo transit estimate nếu OTP không trả itinerary có transit
  leg và geometry.
- OTP luôn cần ngày/giờ khởi hành. Plan có `startDate` dùng ngày của plan; plan
  chưa có ngày dùng ngày hiện tại cùng giờ của leg làm preview. Deployment phải
  nạp OSM và GTFS Schedule; GTFS-RT là tùy chọn nhưng cần thiết nếu muốn thông
  tin realtime.
- UI development được phép hiển thị route OTP có geometry thật với
  `scheduleStatus=development_shifted_2018`, luôn kèm cảnh báo và không đổi
  `verified=false`; ngoại lệ này không áp dụng cho transit estimate.

## Hệ quả

- Không có phí license/API theo request khi self-host, nhưng có chi phí máy chủ,
  cập nhật OSM/GTFS và giám sát dịch vụ.
- Chất lượng bus phụ thuộc trực tiếp vào độ phủ và độ mới của GTFS tại khu vực.
- Valhalla và OTP là hai tiến trình riêng; lỗi của một provider không làm mất
  fallback road hoặc làm hỏng toàn bộ plan.
- `verified=true` chỉ xác nhận route đến từ provider với dữ liệu đã nạp; không
  tự động có nghĩa là traffic/realtime đang mới.
