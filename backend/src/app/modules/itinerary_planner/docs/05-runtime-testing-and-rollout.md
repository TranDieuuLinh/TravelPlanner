# Phase 5: Runtime, route repair, testing và rollout

Trạng thái: đã triển khai route-detail enrichment cho selected arcs và
accommodation transfers, fallback có warning khi thiếu geometry, fallback đường
chim bay khi Valhalla không sẵn sàng, một vòng affected-day repair, timeline validation, public
`ItineraryPlannerOutput`, phase timings và root/API field `plannerOutput`.
Valhalla detail chỉ được gọi sau solver; Planner không query DB và không sửa
PlaceChecker.

## Runtime graph

LangGraph node nên phản ánh các failure boundary, không chia theo từng hàm nhỏ:

```text
prepare_problem
-> build_travel_matrix
-> optimize_hybrid_itinerary
-> enrich_selected_routes
-> finalize_output
```

Trách nhiệm:

```text
prepare_problem       validate/normalize/preflight
build_travel_matrix   provider call, cache, sparse graph
optimize_hybrid_itinerary activity cluster, meal corridor, 2-opt/swap, CP-SAT từng ngày
enrich_selected_routes route detail cho selected arcs và accommodation transfers
finalize_output       sort timeline, totals, warnings, unscheduled
```

Runtime mặc định giữ một CP-SAT search worker cho mỗi daily repair và sparse graph `K=10` theo
`safeTravelMinutes` từ matrix. Forced relationship, meal-access, priority và
component-bridge arcs luôn được union lại sau nearest-neighbor pruning.
Hai solver pass của mỗi ngày có timeout mặc định tương ứng 2 và 5 giây.
Deployment cần SLA khác có thể inject `SolverConfig`. Pass utility dùng relative gap 5%; pass
priority `user_input > URL` vẫn exact trong daily subproblem. Greedy/local-search order được đưa vào
CP-SAT bằng solution hint; CP-SAT vẫn có quyền sửa selection, time và route để
thỏa hard constraint.
Greedy không dùng tổng activity duration làm điều kiện loại sớm. Nó tạo activity
skeleton trước, giữ placeholder cho ba meal, rồi ưu tiên restaurant theo tổng
travel từ activity trước qua restaurant đến activity sau. Daily CP-SAT vẫn sở
hữu kiểm tra duration cùng opening/travel/meal constraints và có thể sửa hint.
Mỗi meal shortlist giữ tối đa ba food option và bảo đảm có ít nhất một
`restaurant` khi top ba ban đầu đều là `drink_dessert` nhưng pool còn restaurant,
giảm fallback full-day do constraint đồ uống/tráng miệng.

Nếu shortlist heuristic vô nghiệm, runtime thử lại ngày đó với toàn bộ candidate
còn khả dụng trong day-domain và hard wait cap 150 phút. Nếu full-day strict
solve vẫn `INFEASIBLE`, runtime retry đúng một lần không hard wait cap nhưng giữ
progressive idle penalty. Nếu pool food unique vẫn làm ngày vô nghiệm, fallback
cuối chỉ mở lại restaurant đã dùng; activity đã dùng vẫn bị loại. Timeout/
`UNKNOWN` không kích hoạt relaxation hay reuse. Khi ghép ngày, Planner kiểm tra
lại explicit budget, tối thiểu 7 giờ nghỉ và thời gian transfer accommodation; vi phạm
trả infeasible, không xuất lịch sai.

Node chỉ đọc/ghi state và gọi service. Retry, timeout và fallback policy nằm
trong service/adapter.

## State nội bộ

`ItineraryPlannerState` nên có:

```text
input
prepared_problem
routing_problem (global matrix + candidate mapping + sparse arcs)
optimization_result
route_details
output
warnings
error
phase_timings_ms
```

Chỉ `input` bắt buộc khi invoke. Các field còn lại được từng node bổ sung.

## Route detail sau solver

Sau pass 3, lấy ordered selected arcs cùng các accommodation transfer đã chọn:

```text
A -> B
B -> C
C -> D
```

Chỉ gọi Valhalla route detail cho các leg này. Driving legs không phụ thuộc
departure time có thể gọi song song trong cùng batch với concurrency limit.
Không gọi geometry cho virtual legs. Accommodation transfer thiếu shape phải
trả warning cụ thể, không chỉ đặt `geometryAvailable=false`.

Output leg nên giữ:

```text
fromPlaceId
toPlaceId
durationMinutes
distanceMeters
encodedPolyline/geometry
provider
```

Turn-by-turn instruction chỉ thêm nếu UI thực sự cần; không làm phình public
contract sớm.

## Route repair

So sánh route detail duration với matrix safe duration. Repair khi:

```text
detail duration > safe matrix duration + tolerance
và timeline bị overlap/vi phạm opening/meal/end-of-day
```

Repair policy:

1. Xác định ngày bị ảnh hưởng.
2. Cập nhật travel coefficient của leg sai lệch.
3. Khóa assignment/route của các ngày không bị ảnh hưởng.
4. Re-solve ngày đó với priority count được bảo vệ tối đa.
5. Chỉ re-enrich route detail của ngày đã thay đổi.

Giới hạn một repair round mặc định để tránh loop. Nếu vẫn không hợp lệ,
trả warning/error có cấu trúc; không âm thầm xuất timeline sai.

## Output contract

Output mục tiêu:

```json
{
  "days": [],
  "totalCostPerPerson": 4200000,
  "budgetPerPerson": 5000000,
  "solver": {
    "status": "feasible",
    "optimalityProven": false,
    "objectiveValue": 123456,
    "planningTimeMs": 8240
  },
  "unscheduled": [],
  "discardedOptionalCount": 12,
  "warnings": []
}
```

`unscheduled` chỉ chứa `user_input` và `url` không được xếp, với reason code
và message. Optional không được chọn chỉ tính count/diagnostic nội bộ,
không làm rác UI.

Implementation còn trả `destination`, `timezone`, ngày thực tế, stop metadata,
ordered route legs, breakdown từng ngày, solver passes,
`objectivePolicyVersion` và `phaseTimingsMs`. API giữ legacy `itinerary` cho
PlanEditor và trả plan mới qua field riêng `plannerOutput`.
Stop metadata giữ `rating`, `reviewCount` và `openingHours` từ candidate đã được
PlaceChecker chuẩn hóa để UI itinerary/map hiển thị dữ liệu DB mà không query
provider trực tiếp.

## Failure policy

```text
invalid contract         -> validation error, không gọi routing
thiếu meal coverage     -> structured planning error trước matrix
Valhalla unavailable     -> straight-line fallback có warning; không giả road travel production
matrix partial           -> loại unreachable arcs, fail nếu priority bị cô lập
daily CP-SAT INFEASIBLE  -> retry full day-domain rồi trả diagnostics
CP-SAT UNKNOWN           -> timeout error nếu chưa có incumbent
CP-SAT FEASIBLE          -> trả plan + optimalityProven=false
route detail partial     -> giữ plan nếu timeline còn hợp lệ, warning leg thiếu geometry
```

Fallback hiện tại dùng khoảng cách Haversine, tốc độ profile cố định và polyline
chỉ gồm điểm đầu/cuối. Đây là ước tính để planner tiếp tục chạy, không phải
quãng đường hoặc thời gian theo đường thật; output luôn có warning.

## Performance budget

Mục tiêu ban đầu, chưa phải SLA cho tới khi benchmark:

```text
3 ngày / 60-80 candidates:   5-12 giây
5 ngày / 100-130 candidates: 8-20 giây
7 ngày / 140-170 candidates: 15-30 giây
```

Phase timing cần ghi riêng:

```text
preprocessing_ms
matrix_ms
sparse_graph_ms
model_build_ms
priority_user_solve_ms
priority_url_solve_ms
utility_solve_ms
route_detail_ms
repair_ms
total_ms
```

Không log raw prompt, full input payload, secret, hoặc raw provider response.

## Test pyramid

### Unit tests

```text
contract aliases và enums
overnight normalization
null opening vs [] closed
feasible-day masks
meal eligibility
quality/preference integer score
relationship one-way dedupe
tag-count diversity thresholds
matrix dedup và asymmetric travel
sparse graph connectivity
```

### Constraint tests

Mỗi hard constraint có một feasible và một infeasible fixture:

```text
duration/opening
no overlap
travel precedence
three meals
candidate uniqueness
budget per person
overnight 03:00 cap
subtour prevention
```

### Lexicographic tests

```text
utility không được hy sinh user_input/URL count
một user_input phải có giá trị hơn toàn bộ URL
pass utility có thể đổi ID nhưng phải giữ locked counts
FEASIBLE timeout không được báo optimal
```

### Golden itinerary tests

Tạo fixture 1/3/5/7 ngày, bao gồm:

```text
culture-heavy preferences nhưng không toàn museum
food không lặp venue/dish
relationship special-near cùng ngày khi hợp lý
overnight nightlife 22:00-03:00
tight budget
missing opening hours
URL/user input conflict
unreachable matrix pair
```

Golden test kiểm invariant và component range, không hard-code từng phút nếu có
nhiều itinerary cùng tối ưu.

### Integration tests

Dùng fake matrix adapter để test graph deterministic. Valhalla adapter contract test
chạy riêng; không để toàn module test phụ thuộc network/container.

## Weight tuning

Không chốt weight từ một ví dụ. Quy trình:

1. Tạo golden dataset và invariant metrics.
2. Chấm schedule bằng review con người.
3. Tune weight theo versioned `ObjectiveWeights` config.
4. So sánh preference match, diversity, travel, meal deviation và priority.
5. Pin `objectivePolicyVersion` trong solver metadata.

Mọi weight change cần regression test; không rải magic number trong constraint files.

## Rollout theo checkpoint

### Checkpoint A: boundary

- Public input/output contract mới.
- Preprocessing và tests.
- Chưa bật runtime root graph.

### Checkpoint B: routing

- Valhalla matrix adapter và fake adapter.
- Sparse arcs, virtual nodes, cache.
- Observability cho matrix.

### Checkpoint C: feasible solver

- Hard constraints và ba bữa.
- Chưa tối ưu utility phức tạp.
- Chứng minh itinerary output luôn hợp lệ.

### Checkpoint D: lexicographic + utility

- Hai pass, warm hints, component breakdown.
- Tags-only diversity, relationship, fatigue/balance.

### Checkpoint E: route detail + repair

- Đã có geometry selected arcs và accommodation transfers, kèm fallback warning
  cụ thể theo leg.
- Đã có affected-day repair tối đa một vòng, khóa ngày không ảnh hưởng và giữ
  số lượng priority.
- Đã có invariant tests; benchmark/golden evaluation quy mô 1/3/5/7 ngày vẫn
  cần chạy với catalog production.

### Checkpoint F: integration

- Root orchestration đã map public upstream JSON sang `ItineraryPlannerInput`
  và trả `plannerOutput` từ Planner.
- Compatibility conversion qua `VerifiedPlace` đã được xóa cùng planner cũ;
  root không tạo itinerary giả trong thời gian các phase mới chưa hoàn tất.
- Backend integration tests dùng fake provider, không gọi network.

Checkpoint F có thể cần sửa tối thiểu ngoài module, nhưng không được đưa
business rule vào orchestration và không sửa PlaceChecker.

## Definition of done

- Module không query DB/Knowledge Graph.
- Không import nội bộ PlaceChecker.
- File source/test/docs không vượt 400 dòng khi có thể tách.
- Module tests, integration tests và `python -m compileall src` pass.
- 100% output itinerary thỏa hard constraints trong property/golden tests.
- Phase timings và solver status có thể audit.
- Tài liệu schema/codebase được cập nhật khi implementation thay public contract.
