# Phase 4: CP-SAT model và solving

Trạng thái: đã triển khai hybrid planner, dùng geographic day-domain,
greedy shortlist, 2-opt/swap và OR-Tools CP-SAT repair theo từng ngày.
CP-SAT repair giữ schedule variables, optional
intervals, opening windows, `AddNoOverlap`, `AddCircuit`, travel precedence,
ba bữa/ngày, budget/người gồm Xanh SM night surcharge, nghỉ liên ngày tối thiểu 7 giờ,
ba pass lexicographic, integer utility và result/component extraction.

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
-> chọn accommodation anchor: rẻ nhất khi có budget, top-1 khi không có target
-> CP-SAT repair ba pass trên từng ngày với endpoint gắn vào anchor
-> ghép ngày, kiểm tra lại budget/rest/transfers của anchor
```

Geographic partition không chạy CP-SAT. `preferred_days` cấp shortlist nhanh;
`feasible_days` vẫn giữ mọi candidate-day hợp lệ làm reserve. Nếu shortlist
không có nghiệm, daily optimizer thử lại với reserve pool đầy đủ trước khi nới
hard wait cap. Preflight không chặn chỉ vì Place trong preferred pool thấp hơn
reserve target: geographic reserve đếm chung Place + Entertainment, còn hard
feasibility chỉ yêu cầu toàn bộ feasible pool giữ ít nhất hai Place mỗi ngày.

Greedy không loại candidate theo tổng `durationMinutes`; nó giữ toàn bộ priority
candidate và lấy optional có điểm tổng hợp cao nhất đến ngưỡng 16 activity.
Điểm này dùng evidence `sourceKind` thật, preference, Bayesian popularity,
quality, relationship và travel-to-current-cluster. Duration,
opening hours và thời gian di chuyển được CP-SAT
kiểm tra khi dựng timeline thật.
Hybrid planner giữ bộ đếm nhóm trải nghiệm của các activity đã được chọn ở
những ngày trước. Shortlist ngày sau trừ điểm nhóm đã xuất hiện và ưu tiên nhóm
mới; candidate nhóm cũ vẫn được lấy lại khi pool không còn đủ nhóm mới.
Điểm quality của shortlist dùng cùng Bayesian review quality với CP-SAT, gồm
rating, review count và prior của candidate pool; popularity bổ sung
`log(reviewCount)` để nhận diện landmark phổ biến mà không cho raw count lấn át.
TravelPlace có Bayesian rating từ 4,2 và ít nhất 500 review nhận thêm 6.000
điểm shortlist để không bị một `Special_Experience` ít review lấn át. CP-SAT
đặt target mềm một popular TravelPlace/ngày; mỗi suất thiếu bị phạt 6.000 utility
để landmark không bị dồn vào một ngày chỉ vì route ngắn hơn.
Breakfast là hard precedence: bữa sáng phải kết thúc trước mọi activity trong
ngày. Skeleton đặt lunch giữa hai cụm và dinner sau activity cuối ngày.
Entertainment được giới hạn tối đa hai/ngày, đồng thời tối đa một trước 12:00
và một từ 18:00. Ở buổi tối, model ưu tiên Special Experience hoặc múa rối
nước; Entertainment đúng loại chỉ nhận fallback reward khi không chọn được hai
nhóm này. Entertainment tùy chọn đã được chọn phải có ít nhất một stop từ
18:00 cùng ngày; nếu có Special Experience/múa rối nước buổi tối thì
Entertainment thường bị loại khỏi ngày đó. Candidate user/URL không chịu rule
fallback này để giữ yêu cầu trực tiếp.

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

Boundary PlaceChecker mới không gửi `DrinkDessert` vào food mà đánh dấu place
bằng tag kỹ thuật `drink_dessert`. Solver giới hạn tổng loại này tối đa hai
điểm/ngày. Constraint meal cho `venueType=drink_dessert` vẫn phục vụ payload cũ.

Route cấm food-to-food arc, nên mỗi ngày phải có activity giữa breakfast/lunch
và lunch/dinner. Strict solve đặt hard maximum `waiting <= 90` phút ngoài
safe-travel buffer. Mốc 5 phút là ideal threshold trong objective; cap ngắn hơn
buộc optimizer dùng activity khả thi để lấp khoảng trống. Nếu cả shortlist và
full-day strict solve đều vô nghiệm, hybrid retry full-day một lần không hard
wait cap; progressive penalty bên dưới vẫn tối thiểu hóa khoảng trống.

Mỗi ngày solver bắt buộc đúng ba bữa, ít nhất hai candidate từ `places`, thưởng
coverage cho mọi `places` khả thi không dùng daily target, và cho phép tối đa một candidate từ pool optional
`entertainment`. Entertainment không được tính thay cho minimum Place.

### Accommodation

Với chuyến nhiều ngày và budget explicit/estimated, hybrid cố định candidate có
chi phí mỗi người thấp nhất trong pool tối đa ba accommodation; không có budget
target thì giữ candidate đầu tiên. Runtime không gọi lại global CP-SAT để đổi
khách sạn sau khi ghép ngày. Chi phí phòng dùng `days - 1` đêm. Ngày `1..days-1` phải
có endpoint route về anchor và ngày `2..days` phải có endpoint route rời anchor.
Daily CP-SAT giữ giờ về trước 03:00 và đưa travel hai chiều vào lower bound của
giờ bắt đầu hôm sau để còn tối thiểu 7 giờ nghỉ. Assembly tạo transfer/cost thật
và kiểm tra lại cùng invariant. Nếu anchor vẫn không hợp lệ, error nêu rõ
`placeId`, ngày và nhóm constraint thất bại thay vì thử global solve.

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

totalCostPerPerson <= trip.budget.amount  # daily CP allocation
```

Khi ghép các ngày, hybrid assembly cho phép tổng cuối vượt tối đa 5% ngân sách
explicit để hấp thụ sai số transfer/làm tròn giữa các ngày; vượt hơn mức này
vẫn trả `hybrid_budget INFEASIBLE`.

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

Trong hybrid có accommodation anchor, `08:00` là giờ sớm nhất rời nơi lưu trú;
stop đầu bắt đầu sau đó ít nhất bằng safe travel time. Validation nghỉ đêm vẫn
trừ cả thời gian quay về accommodation ngày trước và thời gian đi tới stop đầu
ngày sau trước khi kiểm tra minimum 7 giờ.

## Lexicographic solving theo ngày

Dựng model/hard constraints cho từng ngày, solve hai lượt. Vì priority được khóa
trong từng daily repair, metadata không tuyên bố optimality global cho cả chuyến;
`objectivePolicyVersion=hybrid-activity-corridor-v16-dense-activities` và
`optimalityProven=false`.
Mỗi lượt mặc định giữ một CP-SAT search worker. Benchmark local cho thấy hai và
bốn workers đều làm fixture graph nhỏ vượt 90 giây, trong khi single-worker
hoàn tất nhanh; không tăng mặc định nếu chưa có benchmark production theo cỡ
pool. Các hard constraint và thứ tự ưu tiên lexicographic không đổi.
Priority pass giữ exact search không có wall-clock deadline; activity-count
pass có 10 giây và mỗi utility attempt có 10 giây. Activity-count pass khóa
incumbent có nhiều Place fit nhất sau khi đã khóa user/URL. Mỗi utility round chạy ba
solver instance song song, mỗi instance giữ một CP-SAT worker và dùng
`random_seed` khác nhau. Utility giữ incumbent có điểm cao nhất; khi một round
tốt hơn, bộ đếm stagnation được reset. Mặc định trả incumbent sau hai round
liên tiếp không cải thiện; nếu một attempt
chứng minh exact optimum thì dừng ngay. `SolverConfig` vẫn nhận timeout và số
round riêng cho từng môi trường.
Entertainment có hard cap tối đa hai/ngày, tối đa một trước 12:00 và một từ
18:00. Objective vẫn phạt mềm mật độ Entertainment ban ngày, đồng thời cộng
9.000 utility cho Special Experience/múa rối nước bắt đầu từ 18:00. Nếu không
có lựa chọn đó, Entertainment hoặc DrinkDessert chất lượng cao ở buổi tối nhận
7.000 utility fallback.

Mỗi Special Experience được cộng 4.000 utility. Objective đặt target mềm hai
Special TravelPlace/ngày và phạt 10.000 cho mỗi suất thiếu khả thi; hybrid
shortlist cũng reserve loại này theo ngày để route ngắn không loại hết trải
nghiệm đặc sắc. Generic TravelPlace dưới 500 review và food chất lượng thấp chịu
cost riêng. Không có daily activity target hoặc stop-count/active-minute
fatigue penalty; mọi TravelPlace hợp lệ đều nhận coverage utility nếu fit lịch.
Popular TravelPlace có target mềm hai/ngày và shortfall cost 6.000 mỗi suất để
lịch khách lần đầu có nhiều landmark dễ nhận biết hơn.

Với `estimated_daily_cost`, hybrid cho phép biên mềm 5%, trừ tổng tiền lưu trú
của anchor khỏi budget chuyến rồi chia phần còn lại cho từng daily CP-SAT. Mỗi
10.000 VND vượt daily target chịu 500 utility; shortlist mở tối đa sáu phương
án cho mỗi bữa để solver có đủ quán rẻ thay thế. Estimate vẫn mềm để không phá ba
bữa bắt buộc.
Khi có accommodation anchor và budget, hybrid shortlist còn trừ utility theo
chi phí vận chuyển khứ hồi anchor-candidate; cụm xa không được ưu tiên chỉ vì
Special/popular score cao.
Budget-aware shortlist mở lại mọi candidate khả thi trong ngày trước khi rank,
không để geographic preferred-day biến một cụm xa thành lựa chọn bắt buộc.
Food shortlist xếp theo `food price + corridor transport cost` khi có budget,
rồi mới xét travel time và quality; quán gần nhưng quá đắt không chiếm hết sáu
phương án meal.

Pass priority yêu cầu exact optimum để khóa số `user_input` và URL. Pass
activity-count tối đa hóa số Place khả thi không dùng daily target. Pass utility
dùng `relative_gap_limit=0.02`, nên có thể dừng khi utility nằm trong 2% bound;
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

Mỗi lần tag semantic lặp sau candidate đầu tiên tạo same-day cost khi ngày đó
còn nhóm trải nghiệm khác khả thi. Khi alternative đã cạn, tag cũ được dùng lại
không chịu repetition cost. Tag kỹ thuật, generic `travel_place` và style không
tham gia. Tag ngữ cảnh rộng như `văn_hóa`, `địa_phương`, `thiên_nhiên`,
`ẩm_thực`, `đồ_uống`, `indoor`, `outdoor` chỉ dùng preference. Với mỗi route arc activity →
activity, Jaccard overlap của hai tập tag tạo
`consecutiveTagRepetitionCost`; hai stop giống nhau đặt liền nhau bị phạt mạnh
hơn chỉ cùng ngày. Food giữ diversity count riêng.

Ngoài cost trong một ngày, hybrid shortlist theo dõi các nhóm tag của stop đã
thực sự chọn xuyên suốt chuyến đi. Nhóm chưa xuất hiện được ưu tiên trước; đây
không phải hard exclusion, nên nhóm cũ vẫn dùng lại khi alternative đã cạn.

### Travel, waiting và meals

```text
travelTimeCost = sum(arc[i,j,d] * safeTravel[i,j])
waiting = start[j,d] - end[i,d] - safeTravel[i,j]
mealDeviation = abs(mealStart[d,m] - targetStart[m])
```

Waiting chỉ active khi arc được chọn. Strict pass chặn tối đa 90 phút;
relaxed fallback bỏ cap này. Objective luôn phạt lũy tiến: 6-15 phút nhẹ,
16-30 phút mạnh và trên 30 phút rất mạnh; vì vậy solver vẫn ưu tiên fill
activity thay vì để lịch trống, kể cả trong fallback.

Fatigue chỉ giữ penalty cho phần lịch sau 23:00. Day imbalance
dùng chênh lệch activity minutes hoặc stop count; meal duration không tham gia
activity diversity.

## Solver configuration

Config phải inject, không hard-code trong model builder:

```text
num_search_workers
priority_timeout_seconds = None
activity_timeout_seconds = 10
utility_timeout_seconds = 10
utility_relative_gap_limit = 0.02
utility_parallel_workers = 3
max_utility_no_improvement_rounds = 2
random_seed
log_search_progress
max_inter_stop_wait_minutes = 90  # None chỉ dùng cho relaxed fallback
```

Dùng solution pass trước làm hint cho pass sau; hint không thay constraint lock.
Priority pass khóa count ưu tiên, activity-count pass khóa mật độ lịch tối đa.
Utility pass nhận heuristic/baseline hint và tiếp tục cải thiện trong time
budget thay vì dừng ở nghiệm khả thi đầu tiên.
Composition runtime đọc `ITINERARY_LOG_SEARCH_PROGRESS`, mặc định `false`; chỉ
bật khi cần chẩn đoán chi tiết để tránh tạo lượng log OR-Tools lớn. Utility pass
dừng sau hai vòng liên tiếp không cải thiện. Unit test hoặc deployment khác có
thể inject giới hạn riêng qua `SolverConfig`.

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
- Không có food-to-food arc; strict solve giữ waiting không vượt 90 phút và
  relaxed fallback vẫn ghi nhận progressive waiting cost.
- User/URL count không giảm sau pass tương ứng; cost tính per-person.
- Special-near không có selection bonus riêng.
- Relationship một chiều không bị chấm hai lần.
- Tags lặp tạo same-day và consecutive penalty; style là component riêng và
  bằng 0 khi user không yêu cầu.
- Cùng input, seed và matrix cho output deterministic khi solver chứng minh optimum.
