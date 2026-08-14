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

`avoids` được PlaceChecker tiêu thụ trước boundary này. Direct-user place xung
đột vẫn được giữ dạng `conditional` để bảo toàn intent; URL và optional/system
place xung đột bị loại. Compact planner output còn lọc phòng vệ một lần nữa, nên
Planner không nhận `avoids` và không lặp business rule này.

## Các field đầu ra bị cấm

PlaceChecker contract phải từ chối day allocation, selected time slot, route
order, travel leg hoặc final itinerary field.

## Test và điều kiện hoàn thành

Thêm contract snapshot và workflow integration test. Xác nhận provenance và
constraint còn nguyên sau projection. Retrieval/system provisional bị loại;
URL/direct-input identity provisional được giữ kèm `verification_status` và
constraint xác minh. Trách nhiệm hiện tại của FinalItineraryPlanner không đổi.

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
  có canonical ID, tọa độ, provenance và giá dùng được xuống projection. Mandatory blocked vẫn
  nằm trong output và danh sách blocked riêng.
- Projection không chuyển cost `unknown` thành 0. Resolved item và special
  experience được giữ riêng trong rich diagnostic output.
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

Contract gọn dùng camelCase và gồm `trip.timezone`, `startDate`, tách
`places`/`food`, biểu diễn giờ bằng `startMinute`/`endMinute`, thêm
`supportedMeals` cho food. `priority` phân biệt `user_input`,
`special_experience`, `special_near`; `relationships` chứa canonical place ID
liên quan thay vì tên tag.

`startDate` và `timezone` đến từ public `ExplorerOutput`; PlaceChecker không tự
đoán lại ngày. Nếu prompt không có ngày, Explorer dùng ngày mai. Nếu prompt
không có duration, Explorer dùng 3 ngày.

Priority compact luôn thuộc đúng một trong bốn giá trị:

```text
direct_user -> user_input
url         -> url
Special_Near -> special_near
optional còn lại  -> special_experience
```

Root orchestration tạo compact output sau rich `PlaceCheckerResult` và validate
ngay bằng public `ItineraryPlannerInput`. Runtime FinalItineraryPlanner vẫn dùng
compatibility planner cho tới khi routing và CP-SAT hoàn tất; compact payload đã
sẵn sàng trong root state dưới `planner_input`.

`restaurant` và `drink_dessert` được đưa vào `food`; các loại còn lại nằm trong
`places`. Mỗi phần tử có tọa độ, địa chỉ, rating, review count, thời lượng,
giờ mở cửa, quan hệ và `price`.

Food được chọn từ nhánh món đặc trưng có `priority=special_near`, tag
`food-item:<id>`/`food:<name>` và `relationships` chứa TravelPlace anchor.
Rich result giữ FoodItem, Bayesian rating, distance và selection reason để
audit. Nếu restaurant đã có trong food pool, compact builder chỉ gộp anchor và
tag thay vì tạo place ID trùng; candidate thiếu giá, tọa độ hoặc duration vẫn
không vượt qua boundary Planner.

Food pairing ưu tiên giao nhau theo đúng FoodItem ID giữa
`ADM -> Special_Experience -> FoodItem` và
`Restaurant -> Special_Experience -> FoodItem`; adapter không nối theo tên.
Kết quả primary có `foodMatchType=direct_id`. Nếu một anchor không có primary
pair, adapter lấy FoodItem trực tiếp từ `Restaurant -> Offer_Item` và đặt
`foodMatchType=offer_item_fallback`. Fallback không được diễn giải thành món
đặc trưng và không merge entity hoặc tự ghi lại cạnh KG.

PlaceChecker loại mọi place/food không tính được giá trước boundary sang
FinalItineraryPlanner. Giá `price.cost` được tính theo thứ tự:

```text
minimum và maximum đều có -> (minimum + maximum) / 2
chỉ có typical -> typical
chỉ có minimum hoặc maximum -> giá trị đang có
địa điểm free -> 0
không có dữ liệu -> loại, không gửi sang Planner
```

Output chỉ phát `price.cost` và `price.currency` đúng contract JSON của Planner;
`minimum`/`maximum` vẫn được giữ trong rich output nội bộ để phục vụ phân tích
ngân sách. PlaceChecker không tự biến dữ liệu thiếu thành giá miễn phí.
