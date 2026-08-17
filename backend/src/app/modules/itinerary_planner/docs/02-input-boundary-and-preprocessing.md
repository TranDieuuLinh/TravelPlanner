# Phase 2: Input boundary và preprocessing

Trạng thái: đã triển khai Checkpoint A trong module `itinerary_planner`. Public
contract, preprocessing và node `prepare_problem` đã được nối vào graph của
module. Planner cũ đã bị xóa; runtime chưa tạo itinerary cho đến khi Valhalla
và CP-SAT được triển khai.

## Phạm vi

Phase này bắt đầu khi FinalItineraryPlanner nhận JSON `trip + places +
food + foodCoverage`. Module coi dữ liệu upstream là input duy nhất và không:

- query database hoặc Knowledge Graph;
- search thêm place/food;
- sửa PlaceChecker;
- import state, service hoặc contract nội bộ của module khác.

Root orchestration sau này chỉ được map public contract. Mọi fallback,
validation và business rule của Planner phải nằm trong module này.

Với chuyến từ ba ngày và đủ TravelPlace làm geographic anchors, preprocessing
dùng deterministic dense medoids và assignment có capacity. Mỗi optional
candidate thuộc một đến tối đa hai ngày khả thi; mỗi ngày giữ activity reserve
bằng giá trị lớn hơn giữa hai separator và giá trị nhỏ hơn giữa 14 với
`floor(valid_places / days)`. Candidate cô lập không được làm center nếu vùng
20 km quanh nó thiếu reserve. `user_input` và URL giữ nguyên mọi ngày khả thi.
Restaurant có relationship đi theo day-domain của TravelPlace liên kết; sau
projection, meal coverage dùng phép ghép một-một và tự mở lại các food-day gần
nhất cho đến khi breakfast/lunch/dinner được phục vụ bởi ba `placeId` khác
nhau. Một restaurant hỗ trợ cả ba meal type không được tính là ba candidate
riêng. Chỉ khi pool gốc không tồn tại phép ghép ba `placeId` khác nhau,
preprocessing mới tạo meal-occurrence alias nội bộ cho từng slot còn thiếu.
Output ánh xạ alias về `placeId` thật, dùng `itemId` riêng theo meal và phát
warning `Repeated restaurant fallback`.

## Public input contract

JSON bên ngoài dùng camelCase; Pydantic/Python dùng snake_case với alias.

```json
{
  "trip": {
    "destination": "Hanoi",
    "days": 3,
    "startDate": "2026-08-20",
    "timezone": "Asia/Ho_Chi_Minh",
    "people": 2,
    "party": {"adults": 1, "kids": 1},
    "budget": {"amount": 5000000, "currency": "VND"},
    "preferences": {
      "tags": ["culture", "coffee", "local_experience"],
      "avoidTags": ["nightlife"],
      "styles": ["slow_travel"]
    }
  },
  "places": [],
  "food": [],
  "foodCoverage": {
    "days": 3,
    "hardComplete": true,
    "reserveComplete": false,
    "hardAssignments": [],
    "hardMissingSlots": [],
    "reserveAssignments": [],
    "reserveMissingSlots": []
  },
  "upstreamWarnings": []
}
```

Mỗi phần tử `food` có `venueType=restaurant|drink_dessert`; giá trị mặc định
`restaurant` chỉ phục vụ backward compatibility. Runtime PlaceChecker luôn gửi
loại venue rõ ràng để constraint đồ uống/tráng miệng không phụ thuộc tên hoặc
tag tự do.

Mỗi place bắt buộc có:

```text
placeId, name, coordinates, priority, tags, styles, audience, durationMinutes,
openingHours, preferredTimeWindows, price, relationships
```

Mỗi food dùng cùng shape và thêm `supportedMeals`. `tags` là place-type label
phẳng; `styles` tách riêng và chỉ có điểm khi trip yêu cầu style. `audience`
gồm `adultOnly` và `kidSuitable`; unknown không bị tự động coi là không an toàn.
Input legacy `preferences: string[]` vẫn được đọc như `preferences.tags`.

Candidate có thể mang source-owned
`notes={text,sourceType,sourceUrl}`. Planner truyền object này nguyên vẹn sang
stop output, gắn `itemId` ổn định và khởi tạo `personalNotes=null`; Trip Chat
quản lý mutation ghi chú cá nhân sau khi snapshot đã được tạo.

## Pydantic models đã triển khai

Trong `contract.py`, tách các model sau:

```text
TimeInterval(startMinute, endMinute)
Coordinates(latitude, longitude)
PlannerBudget(amount, currency)
PlannerTrip(...)
PlannerPrice(cost, currency)
PlannerCandidate(...)
PlannerFoodCandidate(..., supportedMeals)
PlannerAccommodation(..., coordinates, pricePerNight)
FoodCoverageFeasibility(... hard/reserve assignments và missing slots)
UpstreamCandidateExclusion(..., reasonCode, message)
ItineraryPlannerInput(trip, places, food, foodCoverage, accommodations, excludedCandidates, upstreamWarnings)
```

`PlannerBudget` còn nhận `source`, `dailyEstimate` và `profileVersion`.
`explicit`/legacy `unspecified` amount là hard cap. Amount có
`source=estimated_daily_cost` là approximate soft target; optimizer phạt phần
vượt theo block 10.000 VND nhưng không làm lịch vô nghiệm chỉ vì estimate thấp.

Enum bắt buộc:

```text
CandidatePriority = user_input | url | special_experience | special_near
MealType = breakfast | lunch | dinner
```

`placeId` là ID duy nhất trong toàn bộ `places + food`. Relationship chỉ
chứa ID thuộc tập này. Nếu tương lai có nhiều activity khác nhau tại
cùng physical place thì mới bổ sung `candidateId`; không thêm sớm khi chưa
có use case thật.

Accommodation là pool tối đa ba lựa chọn lưu trú riêng, không nằm trong tập
activity stop và không cần opening/duration. Planner chọn một nơi dựa trên giá
và chặng đi/về lịch. Khi intake chưa có `rooms`, preprocessing suy ra
`ceil(people / 2)` phòng; số đêm là `max(days - 1, 0)`.

## Ý nghĩa opening hours

```json
{
  "openingHours": {
    "1": [{"startMinute": 540, "endMinute": 1050}],
    "2": [],
    "3": null
  }
}
```

Quy ước:

```text
interval có dữ liệu = các khoảng mở cửa của ngày
[]                    = đóng cửa ngày đó
null/thiếu key      = không biết, coi như mở 24 giờ
```

Không được biến `[]` thành mở 24 giờ.

## Validation hai lớp

### Contract validation

Pydantic từ chối toàn request khi:

- `days < 1`, budget âm hoặc currency rỗng;
- trùng `placeId` giữa places và food;
- latitude/longitude ngoài range;
- duration không dương;
- price âm;
- interval ngoài `0..1440` trước khi normalize overnight;
- priority hoặc meal type không thuộc enum.

### Planning validation

`preprocessing.py` phân loại lỗi theo priority:

```text
user_input/url không lập lịch được -> unscheduled candidate + reason
special_experience/special_near lỗi -> discarded optional
```

Whole-trip budget có thể `null`; khi đó phase solver không bật hard budget
constraint. Candidate `price.cost` bắt buộc là số không âm vì PlaceChecker đã
loại place/food thiếu giá và tính `typical_cost` trước boundary. Giá `null` bị
từ chối ngay khi validate `ItineraryPlannerInput`, không đi vào preprocessing.

Reason code nên ổn định:

```text
missing_coordinates
missing_duration
invalid_opening_interval
closed_for_entire_trip
duration_exceeds_every_opening_window
dangling_relationship
unsupported_meal_coverage
```

Relationship trỏ tới ID không tồn tại bị bỏ khỏi index và tạo warning;
không làm hỏng cả request.

## Chuẩn hóa timeline

Timeline mỗi itinerary day:

```text
08:00 hôm nay = 480
23:00 hôm nay = 1380
03:00 hôm sau = 1620
```

Ngày bình thường bị giới hạn tại `480..1380`. Chỉ place có tag nightlife/
drinking trong allowlist mới được dùng phần mở rộng đến `1620`:

```text
22:00-03:00: 1320-180 -> 1320-1620
```

Quy tắc: nếu `endMinute <= startMinute`, cộng 1440 vào end. Sau normalize,
clamp tại `1380` cho candidate thường hoặc `1620` cho late-night candidate.
Interval rỗng bị loại.

Opening hours không biết được coi là mở 24 giờ, nhưng cửa sổ Planner sử dụng là
`480..1380` cho candidate thường và tối đa `480..1620` cho late-night
candidate. Planner gắn cờ `unknown_opening=True` và warning; không ghi ngược
vào input.

## Feasible-day preprocessing

Với candidate `i`, ngày `d` chỉ khả thi nếu tồn tại opening interval:

```text
openingEnd - openingStart >= durationMinutes[i]
```

Kết quả:

```text
feasible_days[i] = {1, 3}
feasible_windows[i, 1] = [...]
feasible_windows[i, 3] = [...]
```

Không tạo biến solver cho ngày không khả thi.

Food còn phải có:

```text
meal in supportedMeals
opening hours overlap meal start window + meal duration
```

Meal policy mặc định:

```text
breakfast: start 08:00-10:00, duration 45, target 08:00
lunch:     start 11:45-13:15, duration 60, target 12:30
dinner:    start 17:45-19:30, duration 60, target 18:30
```

Khoảng cách tối thiểu theo giờ bắt đầu là 180 phút từ breakfast đến lunch và
300 phút từ lunch đến dinner. `mealDeviationCost` tiếp tục kéo từng bữa về gần
giờ mục tiêu trong miền khả thi.

Preflight phải phát hiện nếu một ngày/meal không có food candidate nào
khả thi, thay vì chờ solver trả `INFEASIBLE` không rõ lý do.
Graph trả thêm `errorCode=missing_meal_coverage` và `preflightFailure.missing[]`
gồm `day` cùng `meal`. Đây là public diagnostic để orchestration có thể yêu cầu
PlaceChecker mở rộng đúng phần thiếu; runtime hiện không tự lặp lại toàn bộ
PlaceChecker nếu chưa có expansion provider riêng.

Sau geographic day-domain projection, Planner chạy thêm gate chỉ-đọc. Activity
assignment đã tự cân bằng reserve; gate xác nhận mỗi ngày đạt giá trị nhỏ hơn
giữa 14 và `floor(valid_places / days)`, tối thiểu hai activity để tách ba bữa,
một phép ghép breakfast/lunch/dinner với ba restaurant `placeId` khác nhau, và
opening window còn tồn tại cho mọi candidate-day. Vi phạm trả
`errorCode=projected_pool_preflight_failed` trước khi dựng routing matrix.

Sau khi sparse routing graph được dựng, gate connectivity yêu cầu ít nhất một
weakly-connected component theo ngày chứa hai activity và một distinct
three-meal matching; food-to-food arc không được tính. Vi phạm trả
`errorCode=routing_connectivity_preflight_failed` trước optimizer. Hai gate chỉ
chẩn đoán và dừng sớm, không đổi clustering, day-domain hay meal repair.

## Tags, preference và relationship index

Planner chỉ normalize nhẹ:

```text
trim -> lowercase/casefold -> canonical separator -> deduplicate
```

Planner không dịch hoặc suy diễn tag mới. Input phải là taxonomy upstream đã
chuẩn bị.

Tạo index một chiều:

```python
related_by_place[place_id] = set(relationships)
```

Không tự động thêm reverse edge. Khi tính same-day relationship, một edge
chỉ được chấm một lần.

## Dữ liệu nội bộ sau preprocessing

Nên tạo `PreparedPlanningProblem` không public:

```text
trip
valid_places
valid_food
candidate_by_id
feasible_days
feasible_windows
meal_eligibility
related_by_place
unknown_opening_ids
unscheduled_priority
discarded_optional
warnings
```

Object này là input của routing phase, không serialize qua API.

## File map triển khai

```text
contract.py              public input/output Pydantic models
preprocessing.py         validation nghiệp vụ và PreparedPlanningProblem
time_windows.py          normalize/merge/intersect interval
policies.py              meal windows và planning constants
state.py                 graph state chứa input/prepared/warnings/error
nodes.py                 node mỏng, không chứa rule
public.py                chỉ export public contract/factory
tests/test_contract.py
tests/test_preprocessing.py
tests/test_time_windows.py
```

Không import `app.modules.place_checker.*` trong các file trên.

## Acceptance criteria

- JSON camelCase validate và dump round-trip ổn định.
- Candidate thường kết thúc tối đa 23:00; late-night candidate có thể dùng
  overnight `22:00-03:00` thành `1320-1620`.
- `null` opening thành 24 giờ + warning; `[]` vẫn là closed.
- Cost và budget không nhân với `people`.
- Planner không search DB khi thiếu field.
- Invalid priority candidate có structured reason; invalid optional bị discard.
- Thiếu food cho một meal được phát hiện trước routing/solver.
