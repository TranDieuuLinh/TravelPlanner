# Task 06: Đánh giá từng Place

## Mục tiêu

Đánh giá từng place đã enrich dựa trên destination, people, preference, avoid,
operational status và chất lượng dữ liệu, sau đó tạo state rõ ràng cho Planner.

## Phụ thuộc

Task 04-05. Service không gọi search provider và không lập lịch trình.

## Input và output

`PlaceEvaluationService` nhận danh sách `EnrichedIdentityPlace` và
`TripEvaluationContext`. Mỗi output giữ:

- place cùng provenance;
- lifecycle state và planner eligibility;
- destination compatibility;
- preference matches và avoid conflicts;
- people suitability;
- data completeness/freshness;
- findings có dimension, severity và hard/soft;
- planner constraints và warnings.

Batch chỉ đưa ID của place `planner_ready` hoặc `conditional` vào
`planner_eligible_place_ids`.

## Hard violation

Các trường hợp hiện được coi là hard:

- identity chưa resolve;
- thiếu canonical ID hoặc tọa độ;
- ADM evidence xác định place sai destination;
- `temporarily_closed` hoặc `permanently_closed`;
- metadata xác nhận không phù hợp children/infants có trong đoàn.

Direct-user place có hard violation thành `blocked`. Optional place có hard
violation thành `rejected`.

## Soft finding và planner constraint

- Avoid conflict là soft; optional nightlife bị reject theo policy riêng.
- Direct-user nightlife vẫn giữ ở `conditional` cùng warning.
- Low budget gặp high/premium cost tạo soft budget finding, không tạo số tiền
  hard budget giả.
- Unknown opening hours tạo `verify_opening_hours`, không bị hiểu là closed.
- Thiếu duration tạo `estimate_duration`.
- Reservation bắt buộc tạo `reservation_required`.
- Source time hint tạo `respect_source_time_hint`, chưa chọn time slot.
- Metadata cũ hơn 30 ngày tạo constraint xác minh lại.
- Unknown children/infant suitability chỉ tạo constraint khi đoàn có nhóm đó.

## Data completeness

Completeness hiện xét tọa độ, category, duration, cost, opening hours,
operational status và freshness. Unknown giữ nguyên unknown. Accessibility được
trả trong suitability; input hiện chưa có accessibility requirement riêng nên
không được tự biến thành hard violation.

## State policy

```text
hard violation + mandatory -> blocked
hard violation + optional  -> rejected
optional nightlife avoid   -> rejected
soft finding/constraint    -> conditional
không finding/constraint   -> planner_ready
```

`blocked` và `rejected` không planner-eligible. Direct-user place không bao giờ
bị reject chỉ vì ranking score hoặc soft avoid.

## Giới hạn Checkpoint 3

Task này chưa tính aggregate trip budget, capacity, coverage hoặc gap. Chưa
parse opening-hours thành lịch cụ thể và chưa tính geographic outlier theo bán
kính; ADM mismatch vẫn được kiểm tra từ identity evidence. Các phần đó thuộc
Task 07 và final planning.

## Test và điều kiện hoàn thành

Test gồm planner-ready happy path, direct-user protection, optional nightlife,
closed place, unknown opening hours, children suitability, low-budget conflict,
stale metadata, preference match, destination mismatch và batch eligibility.
