# ADR-012: Route-first itinerary optimizer ở cấp toàn chuyến

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-02

## Bối cảnh

Finder hiện chọn Place theo `DayBrief` rồi mới gọi route optimizer cho từng ngày.
Một ngày bình thường có meal nên legacy optimizer thường phải giữ nguyên toàn bộ thứ
tự. Cách làm này không thể phát hiện hai hoạt động ở hai ngày khác nhau thực ra thuộc
cùng một cụm địa lý, dù chủ đề của hai ngày gần giống nhau.

## Quyết định

Thêm module `app/modules/plans/itinerary_optimizer` sau bước Finder chọn Place:

- runtime đổi Planner thành `TripThemePlannerService`: Planner chỉ trả các
  `tripThemes` phải được phủ ở cấp toàn chuyến, không gán theme hoặc Place cho ngày;
- backend tạo `dayBriefs` trung tính chỉ để tương thích contract cũ; đây là bucket sức
  chứa, không phải quyết định nội dung ngày của Planner;
- theme ngày là tín hiệu mềm để tìm candidate, không tham gia hàm mục tiêu route;
- mỗi ngày route-first có đúng hai activity chính; optimizer được phép hoán đổi
  activity thông thường giữa các ngày nhưng không đổi số slot của ngày;
- stop URL/OCR chỉ bị khóa ngày khi có `sourceDay`; `sourceOrder` giữ thứ tự nguồn,
  còn provenance URL đơn thuần vẫn được phép đổi ngày để gom cụm địa lý;
- ba bữa ăn không tham gia bước chọn/tối ưu activity. Sau khi hai activity đã chốt,
  `MealStopSelector` chọn breakfast gần activity đầu, lunch có độ lệch tuyến nhỏ nhất
  giữa hai activity và dinner gần activity cuối;
- thứ tự ngày cố định là breakfast → activity 1 → lunch → activity 2 → dinner;
- route-first tạm thời không xếp giờ, không lọc theo giờ mở cửa và không chạy
  `TimelineFitter`. `timeWindow` chỉ giữ marker thứ tự nội bộ để tương thích contract cũ,
  không được hiển thị hay diễn giải thành giờ hẹn;
- dùng `TravelTimeMatrixProvider` để giảm tổng thời gian di chuyển của toàn chuyến;
- PlaceSelector không gọi pedestrian/auto/transit leg trong lúc chọn Place; route
  enrichment chi tiết chỉ chạy sau khi allocation và thứ tự cuối cùng đã chốt;
- khi matrix không khả dụng, dùng khoảng cách địa lý; lỗi optimizer giữ nguyên thứ tự
  Finder và route enrichment vẫn chạy qua `GeographicRouteOptimizer` cũ;
- `ITINERARY_OPTIMIZER_MODE=legacy` cho phép quay lại hoàn toàn luồng cũ.

Thuật toán MVP là local search bằng hoán đổi cặp giữa các ngày, sau đó giải chính
xác thứ tự activity trong từng ngày khi có tối đa tám activity. Đây là heuristic
deterministic, không tuyên bố tìm tối ưu toàn cục.

## Hệ quả

- Có thể gom các Place gần nhau dù ban đầu Planner chia chúng sang hai DayBrief.
- Theme hiển thị có thể rộng hơn nội dung từng item; nó không còn là ràng buộc cứng.
- Runtime đổi tên vai trò này thành `PlaceSelectorService`; package/class Finder cũ
  được giữ làm compatibility và rollback boundary, không được xem là một AI agent.
- PlaceSelector vẫn sở hữu candidate selection trong phiên bản này. Candidate-pool discovery
  có thể tách thành module riêng sau khi có evaluation chứng minh shortlist của Finder
  là nút thắt.
- Legacy optimizer được giữ nguyên cho rollback, route enrichment và API chỉ đường.
