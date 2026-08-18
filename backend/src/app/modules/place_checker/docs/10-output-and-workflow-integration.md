# Task 10: Output và tích hợp workflow

Cập nhật lần cuối: 2026-08-18

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
`food_restaurant_selections`, `food_meal_coverage`,
`budget_analysis`, `capacity_analysis`, `coverage_analysis`,
`geographic_analysis`, `gap_analysis`, `unresolved_entities`,
`planner_constraints`, `warnings` và `metadata`.

Mẫu planner-facing minh họa nằm tại
[`output_place_checker.json`](output_place_checker.json). Runtime contract được
khóa bởi `output_contract.py` và contract test; file JSON giúp đọc nhanh một
trường hợp một địa điểm. Luồng Python nội bộ dùng snake_case; HTTP projection
sau này mới đổi alias sang camelCase.

Compact output gửi `foodCoverage` với hard unique assignment cho mọi slot
`day × breakfast/lunch/dinner`, reserve assignment dùng tập Restaurant thứ hai,
và danh sách slot còn thiếu của từng lớp. Đây là feasibility/provenance; việc
đặt bữa vào timeline cuối vẫn thuộc Planner.

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
- Output giữ `styleCandidateSelections[]` với provenance Style, Item và
  relationship source; `styleCandidateCoverage[]` trả target, actual,
  distinct Item và shortfall reason theo từng active Style. Input Style/Item
  không resolve được được trả riêng, không tạo placeholder candidate.
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
  "trip": {
    "party": {"adults": 2, "kids": 1},
    "preferences": {
      "tags": ["history"],
      "avoidTags": ["nightlife"],
      "styles": ["slow_travel"]
    }
  },
  "places": [],
  "food": [],
  "entertainment": null,
  "excludedCandidates": []
}
```

Contract gọn dùng camelCase và gồm `trip.timezone`, `startDate`, tách
`places`/`food`/`entertainment`, biểu diễn giờ bằng `startMinute`/`endMinute`, thêm
`supportedMeals` cho food. Candidate giữ tag phẳng, tách `styles`, và gửi
`audience={adultOnly,kidSuitable}`. `priority` phân biệt `user_input`,
`special_experience`, `special_near`; `relationships` chứa canonical place ID
liên quan thay vì tên tag.

Trước boundary Planner, builder đếm đúng candidate sau toàn bộ filter. Travel
reserve target theo số ngày là quota mềm; thiếu reserve không làm
`PlaceCheckerResult.status=blocked`. Builder không cắt candidate có priority
`user_input`/`url` khi vượt reserve cap, để FinalItineraryPlanner tự chọn và
đưa candidate không xếp được vào `unscheduled`. Food pool chỉ hard-require
`days * 3` candidate meal-capable để tương ứng ba meal slot mỗi ngày. Thiếu
hard meal minimum hoặc candidate bắt buộc không hợp lệ mới block trước Planner.

Scoring tạo TravelPlace reserve bằng coverage mềm: ưu tiên candidate có evidence
`Special_Experience`, sau đó một phần popular theo Bayesian quality kết hợp
`log(reviewCount)`, rồi fill bằng ranking diversity. Phần fill soft-cap một tag
rộng ở tối đa 3 candidate khi còn tag khác để thay thế. Candidate chỉ được chọn
một lần và bucket thiếu tự fallback; Planner vẫn sở hữu geographic/day selection.
Rating và review count được chuẩn hóa trong từng category trước khi tính điểm:
TravelPlace được ưu tiên cao nhất, Restaurant thấp hơn, còn
DrinkDessert/Entertainment thấp nhất vì review volume thường lớn nhưng không
phải mục tiêu chính của lịch tham quan.

`special_near` là ưu tiên, không phải hard gate. Coverage dựa trên relationship
thực tế, không dựa riêng vào `priority`: restaurant đã tồn tại trong food pool
có thể giữ priority mạnh hơn như `user_input` nhưng vẫn được tính là paired sau
khi merge anchor relationship. TravelPlace không có pairing dùng general food
pool đã qua eligibility filter làm fallback để Planner tối ưu theo route và
meal window.
User input hoặc URL candidate không đủ điều kiện planner không bị mất âm thầm;
builder đưa chúng vào `excludedCandidates` với `reasonCode` và message.

`startDate` và `timezone` đến từ public `ExplorerOutput`; PlaceChecker không tự
đoán lại ngày. Nếu prompt không có ngày, Explorer dùng ngày mai. Nếu prompt
không có duration, Explorer dùng 3 ngày.

Priority compact luôn thuộc đúng một trong bốn giá trị:

```text
direct_user -> user_input
resolved inputItem -> user_input
url         -> url
Special_Near -> special_near
optional còn lại  -> special_experience
```

Root orchestration tạo compact output sau rich `PlaceCheckerResult` và validate
ngay bằng public `ItineraryPlannerInput`. Runtime FinalItineraryPlanner vẫn dùng
compatibility planner cho tới khi routing và CP-SAT hoàn tất; compact payload đã
sẵn sàng trong root state dưới `planner_input`.

Chỉ `restaurant` được đưa vào `food`; `drink_dessert` và `entertainment` nằm
trong pool `entertainment` để không chiếm breakfast/lunch/dinner hoặc quota
TravelPlace. Pool optional này có target `4 × days` và trả `null` khi không có
candidate. Mỗi food giữ `venueType=restaurant`. Mỗi phần tử có tọa độ, địa chỉ,
rating, review count, thời lượng, giờ mở cửa, quan hệ và `price`.

Giờ mở cửa trực tiếp của place là hard feasibility boundary. `time_windows` từ
`Has_Style` hoặc `Offer_Item -> ActivityItem` chỉ tạo preferred timing; Style
không được biến thành giờ mở cửa cứng khi place thiếu timing trực tiếp.

Food query lấy một batch trong bán kính tính từ tọa độ tối đa 5 km. Cạnh
`Special_Near` được giữ làm provenance nhưng không còn là điều kiện bắt buộc.
`Restaurant -> Special_Experience -> FoodItem` và
`Restaurant -> Offer_Item -> FoodItem` được đọc song song, không chờ nhánh này
fail mới chạy nhánh kia; `Has_Style` nằm trong metadata relationship evidence.

Sau mỗi query, service dedup `(anchor, restaurant)`, gộp tiếp về một Restaurant,
giữ mọi anchor/evidence, rồi loại candidate thiếu tọa độ, duration, giá hoặc
meal window. Hard coverage cần ít nhất `days * 3` Restaurant duy nhất và ít
nhất `days` candidate hỗ trợ từng loại breakfast/lunch/dinner. Pool ưu tiên
reserve gấp đôi: tối đa `days * 6` Restaurant duy nhất và `days * 2` candidate
cho từng breakfast/lunch/dinner. Khi pool gần 5 km chưa đạt reserve này,
service query general ADM đúng một lần, loại ID đã thấy và chỉ lấy theo deficit
tính từ candidate hợp lệ sau dedup/metadata validation. Pool cuối vẫn bị chặn ở
soft target nên fallback không làm số candidate tăng không giới hạn.
PlaceChecker không phân bổ quán vào ngày; Planner vẫn quyết định meal cuối.

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

Accommodation dùng boundary riêng, không đi vào `places` như activity. Chỉ bản
ghi đã xác minh và có `typical_cost > 0` được chọn. Budget low/medium/high xác
định mốc P25/P50/P80; selector lấy tối đa ba candidate quanh mốc đó rồi xếp lại
theo khoảng cách tới tâm tọa độ của compact TravelPlace pool. Khi có budget
target, hybrid Planner dùng candidate rẻ nhất làm anchor; nếu không mới dùng
candidate đầu tiên. Các candidate còn lại được giữ làm dữ liệu giải thích/dự
phòng ở boundary. Output kèm `coordinates` và `pricePerNight`.

## Budget truyền sang Planner

- Có `targetAmount`: giữ số tiền đã được Explorer chuẩn hóa theo người; direct
  PlaceChecker payload còn `group_total` được chia đúng một lần.
- Không có `targetAmount`: lấy P25/P50/P80 theo budget level từ pool
  Accommodation, Restaurant và TravelPlace đã query trong cây ADM; dùng ba
  bữa/ngày, 2/3/4 activity và 4/5/6 chặng Xanh SM 5 km rồi phát
  `source=estimated_daily_cost`, `dailyEstimate` cùng `profileVersion`.
- Thiếu giá của một pool bắt buộc: giữ `amount=null` và `source=unspecified`,
  không mượn profile của ADM khác.
