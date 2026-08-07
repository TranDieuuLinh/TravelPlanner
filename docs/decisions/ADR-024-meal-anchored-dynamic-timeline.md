# ADR-024: Timeline động với meal anchor mềm

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

ADR-012 giới hạn route-first ở đúng hai activity mỗi ngày và dùng `timeWindow`
như marker thứ tự. Quy tắc theo số lượng không phản ánh thời lượng thật: một tour
dài có thể chiếm gần cả ngày, trong khi nhiều điểm ngắn và gần nhau có thể cùng
vừa một ngày. Pace cũng không phải bằng chứng trực tiếp cho capacity thời gian.

## Quyết định

- Raw prompt và URL luôn dùng chung `meal_anchored_timeline`. Metadata URL chỉ
  thêm source constraint, thứ tự/ngày gợi ý và provenance; nó không chọn một
  skeleton hoặc thuật toán planning khác.
- Finder được phép lấp khoảng trống theo policy `allowFinderGapFill`; địa điểm
  nguồn chỉ được thay thế khi policy độc lập `allowReplaceSourcePlaces` bật.
  Giá trị mặc định cho intake URL là lần lượt `true` và `false`.
- Route-first dùng timeline địa phương 08:00–21:00.
- Breakfast, lunch và dinner có giờ mục tiêu để xếp hạng nhưng là cửa sổ mềm
  (lần lượt khoảng 07:00–09:30, 11:30–14:00 và 17:30–20:00). Activity kéo dài
  hoặc route leg chậm có thể đẩy bữa ăn trong cửa sổ thay vì tạo overlap.
  Khi không resolve được venue ăn, Planner giữ warning thay vì tạo Place giả.
- Activity lấp các khoảng 09:00–12:00, 13:00–18:00 và 19:00–21:00.
- Không giới hạn activity theo count hoặc pace. Capacity được tính từ duration
  nguồn, duration catalog hoặc fallback 90 phút, cộng transition.
- Hai stop `Restaurant` không được đứng liền nhau trong thứ tự hiển thị của một
  ngày. Phải có ít nhất một `activity` hoặc `DrinkDessert` ở giữa; `break` hay
  khoảng trống không được xem là stop phân cách. Checker coi vi phạm là lỗi.
- Candidate được kiểm tra giờ mở cửa tại khung dự kiến khi dữ liệu có sẵn.
- Sau route enrichment, timeline được fit lại bằng duration của route leg. Khi
  thiếu leg provider, dùng transition estimate 15 phút và giữ trạng thái route
  chưa verified theo contract hiện hành.
- Activity chỉ được overflow khi đã vượt cửa sổ mềm của bữa kế tiếp; sau đó trở
  thành `UnscheduledPlace` với `reasonCode=insufficient_time` sau đúng một lần
  thử chuyển sang ngày khả thi khác.
- `OverallChecker` kiểm tra window cùng ngày, overlap và meal anchor; không kiểm
  tra mật độ theo pace.
- Global allocation chỉ dùng matrix để gom cụm/cân bằng duration giữa các ngày.
  Route leg chi tiết luôn được tính và fit riêng theo từng ngày; không nối route
  xuyên qua ranh giới ngày.
- Domain timeline không quyết định hoặc trình bày loại phương tiện. Mode vẫn
  thuộc route enrichment và lựa chọn hiển thị hiện có.

## Hệ quả

- Một ngày có thể có một, hai hoặc nhiều activity tùy duration và transition.
- `timeWindow` route-first trở thành giờ lịch thật và có thể hiển thị cho user.
- Việc đổi giờ ăn mặc định hoặc cho user cấu hình anchor sau này phải đi qua một
  timeline policy thay vì rải constant trong selector/checker.
- Heuristic hiện tại lấp lịch deterministic và không tuyên bố tối ưu toàn cục.
