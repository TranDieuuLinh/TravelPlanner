# ADR-034: Mandatory-first capacity và lazy gap filling

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-10
- Thay thế: phần thứ tự workflow của ADR-030

## Bối cảnh

ADR-030 chạy capacity preflight ngay sau Explorer, trước TripThemePlanner. Vì
vậy required experience được resolve sau preflight không tham gia quyết định
sức chứa. Route-first cũng từng tăng giới hạn catalog lên 250 candidate mỗi
block và nearby graph suggestion có thể bị nâng vào `selectedPlaces`, làm mờ
ranh giới giữa nghĩa vụ với user và candidate hệ thống chỉ đang xem xét.

## Quyết định

Runtime Main Plan dùng thứ tự:

```text
Explorer + Resolve
  -> TripThemePlanner
  -> Mandatory Candidate Pool
  -> Capacity + Day Allocation
  -> Mandatory Placement
  -> Lazy Gap Filling
  -> Timeline + Stop Ordering
  -> Detailed Route Enrichment
  -> CheckOverall
  -> Persist revision
```

- Mandatory pool chỉ gồm URL/user-selected Place, must-visit Place và
  required experience đã resolve.
- `ClusterFirstRepairSolver` chạy sau khi pool này hoàn tất. Trip không khóa
  duration được mở thêm ngày trong memory; trip khóa duration giữ overflow với
  `reasonCode=no_day_capacity`.
- Candidate suggestion không tham gia quyết định tăng ngày.
- PlaceSelector query tối đa một pool nhỏ theo từng gap; mặc định top 5. Nó chỉ
  commit candidate vừa category, timeline và constraint.
- Suggestion không được chọn hoặc bị detailed-route fitting loại không đi vào
  `UnscheduledPlace`. Danh sách này chỉ chứa nghĩa vụ chưa đáp ứng, candidate
  nguồn `needs_review` và required experience chưa resolve.
- TravelTimeMatrix phục vụ capacity/clustering; detailed route enrichment chỉ
  chạy khi stop và thứ tự đã ổn định để lấy duration, distance và geometry.

## Hệ quả

- Required experience được tính cùng source Place trước khi quyết định capacity.
- Suggestion không thể tự làm plan phình thêm ngày.
- User chỉ thấy unscheduled item mà hệ thống thực sự nợ họ.
- Planner giảm catalog load từ hàng trăm candidate mỗi gap xuống một pool bounded.
- Capacity matrix và detailed route vẫn là hai mức dữ liệu khác nhau; không tuyên
  bố đây là một lần gọi route duy nhất.
