# Phase 4: CP-SAT model và solving

Trạng thái: đã triển khai hybrid planner, dùng geographic day-domain,
greedy shortlist, 2-opt/swap và OR-Tools CP-SAT repair theo từng ngày.
CP-SAT repair giữ schedule variables, optional
intervals, opening windows, `AddNoOverlap`, `AddCircuit`, travel precedence,
ba bữa/ngày, budget/người gồm Xanh SM night surcharge, nghỉ liên ngày tối thiểu 7 giờ,
hai pass lexicographic, integer utility và result/component extraction.

## Mục tiêu

Runtime chính không còn đưa toàn bộ candidate-day vào một search tree global.
OR-Tools được pin `>=9.11,<10`, tương thích Python 3.11.

Pipeline chính:

```text
prepared candidates
-> geographic preferred pool (heuristic center + greedy + một lần rebalance)
-> greedy activity cluster từng ngày
-> tạo placeholder breakfast/lunch/dinner quanh activity skeleton
-> chọn food theo corridor activity trước/sau meal
-> 2-opt + swap cải thiện thứ tự activity
-> CP-SAT repair hai pass trên từng ngày
-> ghép ngày, chọn accommodation, kiểm tra budget/rest/transfers
```

Geographic partition không chạy CP-SAT. `preferred_days` cấp shortlist nhanh;
`feasible_days` vẫn giữ mọi candidate-day hợp lệ làm reserve. Nếu shortlist
không có nghiệm, daily optimizer thử lại với reserve pool đầy đủ trước khi nới
hard wait cap.

Greedy không loại candidate theo tổng `durationMinutes`; nó giữ toàn bộ priority
candidate và lấy optional có điểm tổng hợp cao nhất đến ngưỡng 16 activity.
Điểm này dùng evidence `sourceKind` thật, preference, Bayesian popularity,
quality, relationship và travel-to-current-cluster. Duration,
opening hours và thời gian di chuyển được CP-SAT
kiểm tra khi dựng timeline thật.
Điểm quality của shortlist dùng cùng Bayesian review quality với CP-SAT, gồm
rating, review count và prior của candidate pool; popularity bổ sung
`log(reviewCount)` để nhận diện landmark phổ biến mà không cho raw count lấn át.
Skeleton mặc định đặt breakfast trước activity buổi sáng, lunch giữa hai cụm và
dinner sau activity cuối ngày. Không chủ động hint thêm activity sau dinner để
giữ biên nghỉ đêm/transfer accommodation khả thi; CP-SAT vẫn có quyền sửa nếu
opening window hoặc user-input bắt buộc yêu cầu lịch tối.

CP-SAT theo ngày quyết định:

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
hybrid/
├── heuristic.py
├── projection.py
├── optimizer.py
└── assembly.py
```

LangGraph node gọi hybrid optimizer qua worker thread để việc solve CPU-bound
không chặn event loop. `solver.py` vẫn là CP-SAT engine thấp tầng: hybrid gọi nó
cho từng ngày. Route repair thử model global khóa ngày không ảnh hưởng trước;
nếu model đó `INFEASIBLE`, runtime bỏ day locks và hybrid-replan toàn chuyến để
optional candidate có thể được thay hoặc loại.

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
meal policy, không nhân đôi với `durationMinutes` của food input. Một candidate
nội bộ mặc định tối đa một lần trong chuyến:

```text
sum(meal[f,d,m] for all d,m) <= 1
```

Khi và chỉ khi preprocessing chứng minh pool gốc không có unique matching cho
ba meal slot của một ngày, mỗi lần dùng lại venue được biểu diễn bằng một
meal-occurrence alias có `candidateId` riêng và đúng một supported meal. Solver
vẫn giữ constraint trên từng alias; finalization ánh xạ các alias về cùng
public `placeId`, tạo `itemId` khác nhau và giữ warning fallback trong output.

Meal start phải nằm trong flexible start window và toàn bộ interval phải nằm
trong opening hours của food.

Breakfast bị chặn cứng tại 10:00. Trong cùng ngày, lunch phải bắt đầu ít nhất
180 phút sau breakfast và dinner ít nhất 300 phút sau lunch.

Mỗi ngày có tối đa hai food stop mang `venueType=drink_dessert`. Hai meal slot
liền nhau không được cùng chọn `drink_dessert`, nên nếu dùng hai điểm thì chúng
chỉ có thể nằm ở breakfast và dinner. Constraint này bổ sung cho rule route
food-to-food bên dưới; nó kiểm soát loại venue chứ không chỉ thứ tự stop.

Route cấm food-to-food arc, nên mỗi ngày phải có activity giữa breakfast/lunch
và lunch/dinner. Strict solve đặt hard maximum `waiting <= 150` phút ngoài
safe-travel buffer. Mốc 15 phút là ideal threshold trong objective, không còn là
hard gate làm lịch hợp lệ 20-60 phút chờ bị `INFEASIBLE`. Nếu cả shortlist và
full-day strict solve đều vô nghiệm, hybrid retry full-day một lần không hard
wait cap; progressive penalty bên dưới vẫn tối thiểu hóa khoảng trống.

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

Giữa stop cuối ngày `d` và stop đầu ngày `d+1` phải có ít nhất 7 giờ nghỉ:

```text
firstStart[d+1] + 1440 - lastEnd[d] >= 420
```

`420` phút là ngưỡng khả thi tối thiểu, không phải thời lượng nghỉ cố định.
Solver được phép để khoảng nghỉ dài hơn (thường 7-10 giờ) tùy lịch hai ngày.

Ví dụ kết thúc 03:00 (`1620`) thì ngày sau bắt đầu sớm nhất 10:00 (`600`).
Breakfast window được phép trễ đến 12:00 trên recovery day; target 08:00 vẫn
giữ ngày bình thường bắt đầu sớm.

Trong hybrid assembly, `08:00` là giờ bắt đầu stop đầu chứ không phải giờ sớm
nhất được rời accommodation. Transfer có thể bắt đầu trước 08:00; validation
nghỉ đêm vẫn trừ cả thời gian quay về accommodation ngày trước và thời gian đi
tới stop đầu ngày sau trước khi kiểm tra minimum 7 giờ.

## Lexicographic solving theo ngày

Dựng model/hard constraints cho từng ngày, solve hai lượt. Vì priority được khóa
trong từng daily repair, metadata không tuyên bố optimality global cho cả chuyến;
`objectivePolicyVersion=hybrid-activity-corridor-v2` và
`optimalityProven=false`.
Mỗi lượt mặc định giữ một CP-SAT search worker. Benchmark local cho thấy hai và
bốn workers đều làm fixture graph nhỏ vượt 90 giây, trong khi single-worker
hoàn tất nhanh; không tăng mặc định nếu chưa có benchmark production theo cỡ
pool. Các hard constraint và thứ tự ưu tiên lexicographic không đổi.
Hai pass mặc định không đặt `max_time_in_seconds`; solver chạy tới khi chứng minh
optimal/infeasible hoặc gặp lỗi bên ngoài. `SolverConfig` vẫn nhận timeout cụ
thể cho benchmark, test hoặc runtime deployment cần latency cap.
Pass priority yêu cầu exact optimum để khóa số `user_input` và URL. Pass utility
dùng `relative_gap_limit=0.05`, nên có thể dừng khi utility nằm trong 5% bound;
metadata giữ `optimalityProven=false` khi dùng tolerance này, kể cả OR-Tools
trả status `OPTIMAL` theo tolerance.

### Pass 1: priority

```text
maximize userInputCount * (urlCandidateCount + 1) + urlCount
```

Multiplier bảo đảm một `user_input` luôn giá trị hơn toàn bộ URL cộng lại. Nếu
optimum trả `U` user input và `R` URL, khóa riêng cả hai count:

```text
sum(selected[user_input]) = U
sum(selected[url]) = R
```

Khóa count, không khóa ID cụ thể. Pass sau vẫn có thể đổi tổ hợp candidate nếu
giữ đúng `U`, `R` và tạo itinerary tốt hơn.

### Pass 2: plan utility

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
styleValue = matched requested styles / total requested styles * coefficient
placeQualityValue = Bayesian review quality * selected[i]
unknownOpeningCost = small coefficient * selected[i]
```

Nếu không có tag/style preference, component tương ứng bằng 0; không gán
neutral bonus.
Bayesian prior được tính trên candidate pool của planning problem: mean là trung
bình rating có dữ liệu, prior weight là median review count nhưng không thấp hơn
20. Adjusted rating dùng weighted mean; quality 0..1 còn nhân review reliability
với floor 0,70 để candidate ít review không bị loại nhưng không vượt candidate
có rating gần tương đương và lượng review đáng tin. Implementation dùng chung
với PlaceChecker tại `shared/tools/bayesian_rating.py`.

Time fit dùng ba mức integer: full overlap, partial overlap và no overlap.
Opening hours vẫn là hard constraint; preferred window chỉ là objective.

### Same-day relationship

Với edge một chiều `i -> j`, tạo `sameDay[i,j,d]` là AND của hai
assigned variables. Cộng một lần nếu cùng ngày. Không cộng adjacency
bonus; travel penalty đã khuyến khích route gần.

### Diversity chỉ dùng tags phẳng

Không tạo pairwise variable cho mọi candidate. Với canonical tag `t`:

```text
tagCount[t,d] = sum(assigned[i,d] * hasTag[i,t])
```

Mỗi lần tag semantic lặp sau candidate đầu tiên tạo same-day cost. Tag kỹ thuật,
generic `travel_place` và style không tham gia. Với mỗi route arc activity →
activity, Jaccard overlap của hai tập tag tạo
`consecutiveTagRepetitionCost`; hai stop giống nhau đặt liền nhau bị phạt mạnh
hơn chỉ cùng ngày. Food giữ diversity count riêng.

### Travel, waiting và meals

```text
travelTimeCost = sum(arc[i,j,d] * safeTravel[i,j])
waiting = start[j,d] - end[i,d] - safeTravel[i,j]
mealDeviation = abs(mealStart[d,m] - targetStart[m])
```

Waiting chỉ active khi arc được chọn. Strict pass chặn tối đa 150 phút;
relaxed fallback bỏ cap này. Objective luôn phạt lũy tiến: 16-30 phút nhẹ,
31-60 phút mạnh và trên 60 phút rất mạnh; vì vậy solver vẫn ưu tiên fill
activity thay vì để lịch trống, kể cả trong fallback.

Fatigue gồm stop/active-minute threshold và phần lịch sau 23:00. Day imbalance
dùng chênh lệch activity minutes hoặc stop count; meal duration không tham gia
activity diversity.

## Solver configuration

Config phải inject, không hard-code trong model builder:

```text
num_search_workers
priority_timeout_seconds = None
utility_timeout_seconds = None
utility_relative_gap_limit = 0.05
random_seed
log_search_progress
max_inter_stop_wait_minutes = 150  # None chỉ dùng cho relaxed fallback
```

Dùng solution pass trước làm hint cho pass sau; hint không thay constraint lock.
Khi không có wall-clock deadline, priority pass vẫn chứng minh count ưu tiên,
còn utility pass nhận heuristic/baseline hint và dừng ở nghiệm khả thi đầu tiên
để không phải giữ worker chỉ nhằm chứng minh utility tối ưu.
Composition runtime đọc `ITINERARY_LOG_SEARCH_PROGRESS`, mặc định `true`, và
truyền thành `SolverConfig(log_search_progress=True)` để OR-Tools phát progress
log. Runtime mặc định không đặt wall-clock deadline theo yêu cầu vận hành hiện
tại; unit test hoặc deployment khác vẫn có thể inject giới hạn qua `SolverConfig`.

Status gồm `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`. Nếu priority pass chỉ
`FEASIBLE`, output không được tuyên bố count tối đa hay `optimalityProven=true`.

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
- Không có food-to-food arc; strict solve giữ waiting không vượt 150 phút và
  relaxed fallback vẫn ghi nhận progressive waiting cost.
- User/URL count không giảm sau pass tương ứng; cost tính per-person.
- Special-near không có selection bonus riêng.
- Relationship một chiều không bị chấm hai lần.
- Tags lặp tạo same-day và consecutive penalty; style là component riêng và
  bằng 0 khi user không yêu cầu.
- Cùng input, seed và matrix cho output deterministic khi solver chứng minh optimum.
