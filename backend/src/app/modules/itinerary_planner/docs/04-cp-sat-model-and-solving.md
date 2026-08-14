# Phase 4: CP-SAT model và solving

Trạng thái: đã triển khai OR-Tools CP-SAT với schedule variables, optional
intervals, opening windows, `AddNoOverlap`, `AddCircuit`, travel precedence,
ba bữa/ngày, budget/người gồm Xanh SM night surcharge, nghỉ liên ngày 9 giờ,
ba pass lexicographic, integer utility và result/component extraction. Graph đã
có node `optimize_itinerary`; route enrichment/final public output thuộc Phase
5 nên chưa thực hiện ở đây.

## Mục tiêu

CP-SAT nhận prepared candidates, sparse arcs và matrix, sau đó quyết định
toàn bộ itinerary cùng lúc. OR-Tools được pin `>=9.11,<10`, tương thích
Python 3.11.

Planner không chọn top place rồi chèn tuần tự. Solver tìm:

```text
chọn candidate nào
xếp ngày nào
bắt đầu/kết thúc lúc nào
chọn food nào cho meal nào
route nối các stop theo thứ tự nào
```

## Cấu trúc code

Tách model để mỗi file dưới 400 dòng:

```text
optimizer/
├── config.py
├── variables.py
├── routing_constraints.py
├── objective.py
├── solver.py
└── result.py
```

LangGraph node gọi optimizer qua worker thread để việc solve CPU-bound không
chặn event loop. `solver.py` điều phối ba pass; công thức CP-SAT chi tiết nằm
trong các file optimizer chuyên trách.

## Biến quyết định

Chỉ tạo biến cho feasible days/arcs:

```text
selected[i]          Bool
assigned[i,d]        Bool
start[i,d]           Int minutes
end[i,d]             Int minutes
usesWindow[i,d,w]    Bool
arc[i,j,d]           Bool
meal[f,d,m]          Bool
mealStart[d,m]       Int minutes
```

Liên kết selection/day:

```text
selected[i] = sum(assigned[i,d] for feasible d)
sum(assigned[i,d]) <= 1
```

Mỗi activity có optional interval dùng `assigned[i,d]` là presence literal.

## Hard constraints

### Duration và opening window

Khi `assigned[i,d] = 1`:

```text
end[i,d] = start[i,d] + duration[i]
sum(usesWindow[i,d,w]) = assigned[i,d]
```

Với window được chọn:

```text
start[i,d] >= openingStart[i,d,w]
end[i,d]   <= openingEnd[i,d,w]
```

Dùng `OnlyEnforceIf(usesWindow)`; không dùng big-M khi CP-SAT có enforcement
literal tương ứng.

### No overlap

`AddNoOverlap` trên optional intervals của activity và meal trong từng ngày.
NoOverlap chỉ chặn stop trùng nhau; travel precedence bên dưới mới bảo đảm
có thời gian di chuyển.

### Route và travel precedence

Khi `arc[i,j,d] = 1`:

```text
start[j,d] >= end[i,d] + safeTravel[i,j]
```

Mỗi selected node có đúng một incoming và một outgoing arc. Mỗi ngày có
virtual START/END. Để dùng `AddCircuit`, thêm arc nội bộ `END -> START`
không có time/cost; self-loop biểu diễn node không thuộc ngày. Arc nội bộ
không xuất output.

Phải có test chống subtour, ví dụ không cho phép:

```text
START -> A -> END
B -> C -> B
```

### Meals

Mỗi `day, mealType`:

```text
sum(meal[f,d,m] for eligible food f) = 1
```

Food được chọn trở thành route node và optional interval. Duration theo
meal policy, không nhân đôi với `durationMinutes` của food input. Một venue
mặc định tối đa một lần trong chuyến:

```text
sum(meal[f,d,m] for all d,m) <= 1
```

Meal start phải nằm trong flexible start window và toàn bộ interval phải nằm
trong opening hours của food.

Breakfast bị chặn cứng tại 10:00. Trong cùng ngày, lunch phải bắt đầu ít nhất
180 phút sau breakfast và dinner ít nhất 300 phút sau lunch.

Route cấm food-to-food arc, nên mỗi ngày phải có activity giữa breakfast/lunch
và lunch/dinner. Mỗi selected arc còn có `waiting <= 15` ngoài safe-travel
buffer; pool/opening window không đủ thì trả `INFEASIBLE` thay vì ngày chỉ có meal.

### Accommodation

Với chuyến nhiều ngày, solver chọn đúng một candidate trong pool tối đa ba
accommodation. Chi phí phòng dùng `days - 1` đêm. Ngày `1..days-1` kết thúc ở
accommodation và ngày `2..days` bắt đầu từ đó; các transfer này tham gia travel
time và transport cost. Transfer trên 50 km nhận relocation penalty mạnh để
ưu tiên accommodation gần cụm lịch hơn, nhưng không làm toàn bài toán vô nghiệm
khi mọi lựa chọn đều xa.

### Source mix sáng/tối

Activity kết thúc không muộn hơn 12:00 được tính vào morning; activity bắt đầu
từ 18:00 được tính vào evening. Afternoon không tham gia quota. Trong mỗi buổi,
solver đặt target Special Experience bằng largest-remainder: 70% morning và
60% evening; phần còn lại là Offer Item. Candidate `both` có hai choice literal
với tổng bằng period literal nên chỉ được đếm một lần.

Độ lệch actual/target khả thi là soft `sourceMixDeviationCost`; target dùng
trong objective được clamp theo số candidate từng nguồn có thể vừa buổi đó để
thiếu dữ liệu không bị phạt và Offer có thể bù Special. Output vẫn giữ tỷ lệ
policy chưa clamp bên cạnh actual và cờ fallback để audit phần thiếu. Opening
hours vẫn là hard constraint; source mix không được kéo candidate sang buổi mà
place không hoạt động.

### Budget một người

```text
totalCostPerPerson =
    sum(selectedPlace * placeCost)
  + sum(selectedMeal * foodCost)
  + sum(selectedArc * transportCostPerPerson)

totalCostPerPerson <= trip.budget.amount  # explicit budget only
```

Không nhân với `trip.people`. Price không bị trừ thêm trong objective trừ
khi sản phẩm sau này có yêu cầu "càng rẻ càng tốt".

### Overnight

Candidate thường phải kết thúc trong `480..1380`. Chỉ ID nằm trong
`late_night_eligible_ids` mới được kết thúc muộn hơn 23:00, tối đa `1620`, và
vẫn phải nằm trong opening window.

Giữa stop cuối ngày `d` và stop đầu ngày `d+1` phải có ít nhất 9 giờ nghỉ:

```text
firstStart[d+1] + 1440 - lastEnd[d] >= 540
```

Ví dụ kết thúc 03:00 (`1620`) thì ngày sau bắt đầu sớm nhất 12:00 (`720`).
Breakfast window được phép trễ đến 12:00 trên recovery day; target 08:00 vẫn
giữ ngày bình thường bắt đầu sớm.

## Lexicographic solving

Dựng model/hard constraints một lần, solve ba lượt.

### Pass 1: user input

```text
maximize sum(selected[i] where priority=user_input)
```

Nếu optimum là `U`, thêm:

```text
sum(selected[user_input]) = U
```

Khóa count, không khóa ID cụ thể. Pass sau có thể đổi tổ hợp user input
nếu vẫn giữ count `U` và tạo itinerary tốt hơn.

### Pass 2: URL

```text
maximize sum(selected[i] where priority=url)
```

Giữ constraint user input. Nếu optimum là `R`, thêm:

```text
sum(selected[url]) = R
```

### Pass 3: plan utility

Giữ cả `U` và `R`, sau đó:

```text
maximize planUtility
```

Mỗi pass tìm một schedule hoàn chỉnh; không đoán count từ score.

## Objective

CP-SAT chỉ nhận integer. Scale các score 0..100 thành integer coefficient
theo một `SCORE_SCALE` cố định.

```text
planUtility =
    specialExperienceValue
  + preferenceValue
  + placeQualityValue
  + timeFitValue
  + sameDayRelationshipValue
  - activityDiversityCost
  - foodDiversityCost
  - travelTimeCost
  - accommodationRelocationCost
  - accommodationPriceCost
  - idleWaitingCost
  - mealDeviationCost
  - fatigueCost
  - dayImbalanceCost
  - unknownOpeningCost
```

Không có `specialNearBonus`: special-near chỉ được lợi khi relationship được
tận dụng.

### Candidate values

```text
specialExperienceValue = coefficient * selected[i]
preferenceValue = matched preferences / total preferences * coefficient
placeQualityValue = Bayesian review quality * selected[i]
unknownOpeningCost = small coefficient * selected[i]
```

Nếu không có preferences, preference value bằng 0; không gán neutral bonus.
Bayesian prior được tính trên candidate pool của planning problem: mean là trung
bình rating có dữ liệu, prior weight là median review count nhưng không thấp hơn
20. Adjusted rating dùng weighted mean; quality 0..1 còn nhân review reliability
với floor 0,70 để candidate ít review không bị loại nhưng không vượt candidate
có rating gần tương đương và lượng review đáng tin. Implementation dùng chung
với PlaceChecker tại `shared/tools/bayesian_rating.py`.

### Time fit

Tạo match variable khi selected interval overlap preferred window. Bản đầu có
thể dùng ba mức integer để model gọn:

```text
full overlap    -> full value
partial overlap -> partial value
no overlap      -> 0
```

Opening hours vẫn là hard constraint; preferred window chỉ là objective.

### Same-day relationship

Với edge một chiều `i -> j`, tạo `sameDay[i,j,d]` là AND của hai
assigned variables. Cộng một lần nếu cùng ngày. Không cộng adjacency
bonus; travel penalty đã khuyến khích route gần.

### Diversity chỉ dùng tags

Không tạo pairwise variable cho mọi candidate. Với canonical tag `t`:

```text
tagCount[t,d] = sum(assigned[i,d] * hasTag[i,t])
```

Tạo threshold variables cho lần lặp thứ 2/3/4. Cấu hình tag group:

```text
strong: museum, shopping, nightlife, spa, sightseeing, hands_on
medium: indoor, outdoor, walking, performance, photography
light: culture, history, nature, local_experience
```

Strong repeat phạt nhiều hơn light repeat. Food tách count theo venue/dish/cuisine;
lặp venue phạt mạnh nhất.

### Travel, waiting và meals

```text
travelTimeCost = sum(arc[i,j,d] * safeTravel[i,j])
waiting = start[j,d] - end[i,d] - safeTravel[i,j]
mealDeviation = abs(mealStart[d,m] - targetStart[m])
```

Waiting chỉ active khi arc được chọn, bị chặn cứng tối đa 15 phút; objective vẫn
giữ component waiting để audit.

### Fatigue và day balance

Fatigue có thể gồm:

```text
stop count vượt comfortable threshold
active minutes vượt comfortable threshold
minutes kết thúc sau 23:00
chuỗi activity dài không có rest/meal
```

Day imbalance dùng chênh lệch activity minutes hoặc stop count giữa ngày dày
nhất và ngày nhẹ nhất. Không tính meal duration vào activity diversity.

## Solver configuration

Config phải inject, không hard-code trong model builder:

```text
num_search_workers
pass1_timeout_seconds = 30
pass2_timeout_seconds = 30
pass3_timeout_seconds = 30
random_seed
log_search_progress
```

Dùng solution pass trước làm hint cho pass sau; hint không thay constraint lock.
Composition runtime đọc `ITINERARY_LOG_SEARCH_PROGRESS`, mặc định `true`, và
truyền thành `SolverConfig(log_search_progress=True)` để OR-Tools phát progress
log. Unit test có thể inject config `false` để giữ output gọn.

Status:

```text
OPTIMAL    -> optimum đã được chứng minh
FEASIBLE   -> có schedule, chưa chứng minh tối ưu
INFEASIBLE -> không có schedule theo model hiện tại
UNKNOWN    -> timeout/error trước khi có schedule
```

Nếu pass priority chỉ `FEASIBLE`, có thể khóa incumbent count để tiếp tục nhưng
output phải `optimalityProven=false`; không tuyên bố count là tối đa đã
chứng minh.

## Result extraction

Chỉ đọc kết quả pass cuối:

```text
selected IDs
day assignment
start/end
meal type và food
ordered selected arcs
total cost per person
objective component breakdown
solver status/timing
```

Output giải thích được phải giữ component totals, không chỉ một utility
number không thể audit.

## Acceptance criteria

- Solver không vi phạm duration/opening/travel/budget/meal constraints.
- Không có food-to-food arc; waiting giữa hai stop liên tiếp không vượt 15 phút.
- User/URL count không giảm sau pass tương ứng; cost tính per-person.
- Special-near không có selection bonus riêng.
- Relationship một chiều không bị chấm hai lần.
- Tags lặp tạo convex penalty; raw style không xuất trong model.
- Cùng input, seed và matrix cho output deterministic khi solver chứng minh optimum.
