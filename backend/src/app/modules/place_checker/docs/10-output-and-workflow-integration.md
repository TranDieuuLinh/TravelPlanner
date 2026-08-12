# Task 10: Output và tích hợp workflow

## Mục tiêu

Đưa ra PlaceChecker output hướng production và chèn stage sau Explorer mà
không kéo trách nhiệm itinerary lên upstream.

## Phụ thuộc

Task 01-09.

## Các nhóm output

- trip context;
- checked place và planner-eligible ID;
- resolved item và special experience có nguồn;
- coverage, gap, budget và geographic analysis;
- unresolved entity, warning và planner constraint;
- execution metadata, cache/tool count và version identifier.

Top-level contract hiện tại đúng theo file mẫu:
`schema_version`, `status`, `trip_context`, `checked_places`,
`planner_eligible_place_ids`, `resolved_items`, `special_experiences`,
`budget_analysis`, `capacity_analysis`, `coverage_analysis`,
`geographic_analysis`, `gap_analysis`, `unresolved_entities`,
`planner_constraints`, `warnings` và `metadata`.

Mẫu planner-facing minh họa nằm tại
[`output_place_checker.json`](output_place_checker.json). Runtime contract được
khóa bởi `output_contract.py` và contract test; file JSON giúp đọc nhanh một
trường hợp một địa điểm. Luồng Python nội bộ dùng snake_case; HTTP projection
sau này mới đổi alias sang camelCase.

Mỗi checked place gồm canonical identity, tọa độ, destination, source tier,
mandatory/removable policy, priority, category/experience, duration, cost,
opening/time constraint, preference/avoid result, people suitability, hard/soft
constraint, verification, confidence, score, provenance, warning, promotion
status và lifecycle state.

## Luồng tích hợp

```text
Explorer output
-> PlaceCheckerInput projection
-> PlaceCheckerService.check
-> PlaceCheckerOutput
-> SelectedPlaceContext/PlaceSelectionInput projection
-> TripThemePlanner và PlaceSelector
```

Chỉ `planner_ready` và `conditional` place được đưa vào planning projection.
Mandatory place bị blocked/unresolved vẫn hiển thị trong PlaceChecker output và
tạo warning cho Planner/user.

## Các field đầu ra bị cấm

PlaceChecker contract phải từ chối day allocation, selected time slot, route
order, travel leg hoặc final itinerary field.

## Test và điều kiện hoàn thành

Thêm contract snapshot và workflow integration test. Xác nhận provenance và
constraint còn nguyên sau projection, provisional place bị loại và trách nhiệm
hiện tại của FinalItineraryPlanner không thay đổi.

## Hiện thực tại Checkpoint 6

- `PlaceCheckerPipeline` ghép Task 01-09 theo thứ tự: context, identity/item,
  evidence/metadata, evaluation, aggregate gap, targeted retrieval, scoring,
  reranking và aggregate lại sau khi thêm optional candidate.
- `PlaceCheckerResult` là output V1 nội bộ. `checked_places[]` được làm phẳng
  đúng cấu trúc JSON mẫu nhưng vẫn giữ identity, evaluation, verification,
  ranking và provenance. Runtime giữ một evaluation nội bộ bị loại khỏi JSON để
  tạo planning projection mà không làm lộ field thừa.
- `ExplorerInputProjector` chuyển contract Explorer legacy hiện tại sang input
  canonical. Explorer mới có thể truyền thẳng `PlaceCheckerInput`.
- `PlaceCheckerPlanningProjector` chỉ đưa `planner_ready/conditional` đã verify,
  có canonical ID, tọa độ và provenance xuống projection. Mandatory blocked vẫn
  nằm trong output và danh sách blocked riêng.
- Projection giữ cost/duration nullable và cost tier `unknown`; không chuyển
  unknown thành 0. Resolved item và special experience được giữ riêng.
- `build_place_checker_pipeline_graph` cho phép orchestration bật pipeline V1
  bằng dependency đã cấu hình mà không đưa business rule vào root graph.

Root graph mặc định vẫn chạy compatibility `PlaceCheckerService` vì repository
hiện chưa có production ADM/KG/metadata/external adapter. Việc bật pipeline V1
ở runtime phải inject các dependency thật; không thay đổi contract hoặc code của
FinalItineraryPlanner trong checkpoint này.

## Output gọn cho FinalItineraryPlanner

`PlaceCheckerPlannerOutputBuilder` tạo thêm dạng JSON gọn theo mẫu tích hợp:

```json
{
  "trip": {},
  "places": [],
  "food": []
}
```

`restaurant` và `drink_dessert` được đưa vào `food`; các loại còn lại nằm trong
`places`. Mỗi phần tử có tọa độ, địa chỉ, rating, review count, thời lượng,
giờ mở cửa, quan hệ và `price`.

Giá `price.cost` được tính theo thứ tự:

```text
minimum và maximum đều có -> (minimum + maximum) / 2
chỉ có typical -> typical
địa điểm free -> 0
không có dữ liệu -> null
```

`minimum` và `maximum` vẫn được giữ nguyên trong JSON để Planner biết khoảng
giá. PlaceChecker không tự biến dữ liệu thiếu thành giá miễn phí.
