# ADR-014: TripThemePlanner không sở hữu lịch ngày

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-03

## Bối cảnh

Flow cũ yêu cầu LLM Planner tạo `MacroPlan` và `DayBrief`, sau đó Finder lại
chọn Place và dựng lịch. Hai tầng cùng sở hữu cấu trúc ngày làm contract dễ lỗi:
LLM có thể trả thiếu/sai ngày, trong khi Finder vẫn cần tự điều chỉnh theo
capacity, source order và route. `TripThemePlannerService` mới chỉ cần xác định
những trải nghiệm phải có ở cấp toàn chuyến; Finder cũng đã được thay bằng
PlaceSelector.

## Quyết định

Runtime dùng flow:

```text
Explorer -> TripThemePlanner -> PlaceSelector -> Checker
```

- TripThemePlanner trả `TripThemePlanningOutput` gồm `tripThemes`, assumption,
  warning và trace. Nó không trả ngày, journey phase hoặc place allocation.
- PlaceSelector nhận `tripSpec.days`, `tripThemes` và `selectedPlaces`; nó tạo
  day slot deterministic, áp capacity, chọn Place và tối ưu tuyến.
- `Plan` lưu trực tiếp `tripThemes` và `days`; dữ liệu mới không ghi
  `macroPlan`.
- Backup Plan dùng lại theme của Main Plan và chạy lại PlaceSelector với
  constraint dự phòng, không gọi lại LLM theme.
- Package runtime `plans/planner` và `plans/finder` bị loại bỏ; code chuyển sang
  `plans/trip_theme_planner` và `plans/place_selector`.
- Adapter chỉ-đọc nhận snapshot cũ có `macroPlan.tripThemes`. Request cũ dùng
  `allowFinderSuggestions` hoặc `allowPlaceSuggestions` vẫn được nhận như alias
  của `allowFinderGapFill`; response mới tách `allowFinderGapFill` khỏi
  `allowReplaceSourcePlaces`.

## Hệ quả

- LLM không còn có thể làm fail planning chỉ vì thiếu hoặc sai `DayBrief`.
- Số ngày luôn lấy từ `tripSpec.days` và có một owner duy nhất.
- Việc xếp Place, overflow và route có thể test deterministic độc lập với LLM.
- Golden dataset và timing stage dùng tên `trip_theme_planner` và
  `place_selector`.
- Source code lịch sử trong plan đã lưu vẫn được đọc để giữ tương thích; chúng
  không phải tên module runtime mới.
