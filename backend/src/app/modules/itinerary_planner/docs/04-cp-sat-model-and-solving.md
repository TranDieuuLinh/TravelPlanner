# Phase 4: CP-SAT model và solving

## Mục tiêu

CP-SAT nhận prepared candidates, sparse arcs và matrix, sau đó quyết định
toàn bộ itinerary cùng lúc. OR-Tools chưa có trong dependency hiện tại;
implementation phải thêm package `ortools` và pin range tương thích Python 3.11.

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
├── variables.py
├── constraints.py
├── meals.py
├── routing.py
├── diversity.py
├── objective.py
├── solver.py
└── result.py
```

`service.py` điều phối preprocessing -> matrix -> optimizer -> route detail;
không chứa công thức CP-SAT chi tiết.

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

### Budget một người

```text
totalCostPerPerson =
    sum(selectedPlace * placeCost)
  + sum(selectedMeal * foodCost)
  + sum(selectedArc * transportCostPerPerson)

totalCostPerPerson <= trip.budget.amount
```

Không nhân với `trip.people`. Price không bị trừ thêm trong objective trừ
khi sản phẩm sau này có yêu cầu "càng rẻ càng tốt".

### Overnight

Mọi start/end nằm trong `480..1620`. Activity kết thúc sau 23:00 vẫn hợp
lệ nếu opening window cho phép, nhưng sẽ có fatigue cost.

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
placeQualityValue = rating quality có review confidence * selected[i]
unknownOpeningCost = small coefficient * selected[i]
```

Nếu không có preferences, preference value bằng 0; không gán neutral bonus.

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

Waiting chỉ active khi arc được chọn. Cho một free-rest threshold nhỏ, ví dụ
15 phút, để solver không nhồi lịch quá kín.

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
pass1_timeout_seconds
pass2_timeout_seconds
pass3_timeout_seconds
random_seed
log_search_progress
```

Dùng solution pass trước làm hint cho pass sau; hint không thay constraint lock.

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
- User input count không giảm sau pass 1; URL count không giảm sau pass 2.
- Cost tính cho một người, không nhân `people`.
- Special-near không có selection bonus riêng.
- Relationship một chiều không bị chấm hai lần.
- Tags lặp tạo convex penalty; raw style không xuất trong model.
- Cùng input, seed và matrix cho output deterministic khi solver chứng minh optimum.
