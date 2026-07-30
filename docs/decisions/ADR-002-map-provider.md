# ADR-002: Lựa chọn nhà cung cấp bản đồ và địa điểm

- Trạng thái: Đã chấp nhận một phần
- Ngày: 2026-07-27
- Cập nhật: 2026-07-30

## Bối cảnh

Bản đồ, chuẩn hóa địa điểm, tuyến đường, thời gian di chuyển và gợi ý phương tiện
là năng lực cốt lõi của MVP. Độ phủ và điều khoản provider có thể ảnh hưởng lớn
đến domain model, UX, chi phí vận hành và khả năng offline.

## Quyết định

Không gắn chặt code sản phẩm trực tiếp với một provider.

HERE Routing API v8 được chọn cho route A → B của Planner/Finder. Backend gọi
`pedestrian` cho lựa chọn đi bộ và `car` cho lựa chọn xe công nghệ. Route dùng
`routingMode=fast`, trả summary và polyline; vì contract plan chưa có ngày đi,
request dùng `departureTime=any` để không áp traffic hiện tại sai cho một chuyến
đi tương lai chưa xác định. Khi plan có ngày/giờ địa phương đầy đủ, quyết định
traffic-aware phải được bổ sung riêng.

HERE Public Transit API v8 được dùng như lựa chọn thứ ba khi
`tripSpec.startDate` có giá trị. Finder kết hợp ngày thứ N với giờ kết thúc item
đầu để gửi `departureTime`; route transit bao gồm đoạn đi bộ ra/vào trạm, thời
gian chờ, các section bus/rail và geometry. Nếu user ưu tiên `bus` hoặc `train`,
transit khả thi được chọn làm leg chính; nếu không, nó nằm trong
`transportLeg.alternatives`. `avoidModes` có quyền loại walk, car hoặc transit.
Không có ngày đi thì không gọi Transit API, vì mặc định của HERE là lịch chạy
tại thời điểm hiện tại.

Finder vẫn giữ policy đi bộ tối đa 1.500 m. Nó kiểm tra tuyến đi bộ HERE trước;
nếu dài hơn ngưỡng thì lấy tuyến car. Mỗi leg HERE thành công có
`source=here_routing_v8`, `verified=true`, `fetchedAt` và geometry thật. Timeout,
quota, response lỗi hoặc thiếu credential chỉ làm leg tương ứng fallback về
`source=geodesic_estimate`, `verified=false`; không làm hỏng toàn bộ plan.
Transit thành công dùng `source=here_transit_v8`, giữ mode/line trong `details`
và cùng provenance/freshness như leg road.

Thứ tự stop chưa có source itinerary vẫn dùng nearest-neighbour và 2-opt theo
tọa độ. HERE hiện xác minh từng leg sau khi xếp thứ tự; chưa dùng Matrix Routing
hoặc Waypoints Sequence để tối ưu toàn cục. Itinerary có thứ tự nguồn tiếp tục
được giữ nguyên.

Trong thời gian benchmark, Explorer được phép dùng HERE Discover như adapter
POI thử nghiệm với Nominatim làm fallback. Việc này không chấp nhận HERE làm
provider bản đồ nền hoặc place resolver duy nhất. Cấu hình phải cho phép quay về
Nominatim mà không đổi contract domain; thiếu HERE credential cũng phải dùng
Nominatim an toàn. Bản đồ nền UI tiếp tục dùng OpenStreetMap/Leaflet và hiển thị
attribution HERE khi có geometry route HERE.

Gateway của provider phải cung cấp:

- tìm kiếm/chi tiết địa điểm và ánh xạ tới place nội bộ ổn định;
- ma trận tuyến đường và geometry tuyến;
- phương tiện được hỗ trợ cùng thời lượng/khoảng cách;
- attribution và metadata về độ mới;
- lỗi có type cho quota, timeout, not-found và phương tiện không hỗ trợ.

## Tiêu chí đánh giá

Chấm điểm ứng viên theo độ phủ tại Việt Nam, chất lượng transit/phương tiện địa
phương, độ chính xác khi đi bộ/lái xe, giá, quota, điều khoản cache/hiển thị, khả
năng tiếp cận, độ trễ và chất lượng SDK.

## Hệ quả

- Một interface nhỏ giúp giảm phụ thuộc provider và cho phép dùng fake khi test.
- Cần benchmark tiếp Matrix/Waypoints Sequence trước khi đổi thuật toán sắp thứ
  tự stop sang dữ liệu thời gian đường thực.
- Tính năng riêng của provider có thể tồn tại trong adapter nhưng không được rò
  rỉ vào plan entity hoặc contract API công khai.
- Hạn mức và pricing của plan provider là dữ liệu vận hành có thể thay đổi,
  không được hard-code quota thương mại vào domain hoặc tuyên bố thành SLA.
- Route chưa traffic-aware cho đến khi plan có ngày đi; `verified=true` chỉ có
  nghĩa distance/duration/geometry đến từ HERE, không có nghĩa là ETA live.
