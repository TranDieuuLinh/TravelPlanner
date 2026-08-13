# Phase 3: Valhalla matrix và sparse arcs

Trạng thái: đã triển khai routing ports/models, Valhalla HTTP adapter, route
detail adapter, in-memory bounded cache, coordinate deduplication, directed
global matrix, safe travel values, time-feasibility pruning, sparse/forced/
bridge arcs và virtual START/END. Graph đã có node `build_travel_matrix` qua
dependency injection. Nếu thiếu matrix provider hoặc transport cost estimator,
Planner trả lỗi có cấu trúc và không dùng estimated fallback.

## Mục tiêu

Routing phase nhận `PreparedPlanningProblem`, lấy travel time/distance một
lần và tạo graph arc gọn cho CP-SAT. Phase này không chọn itinerary.

```text
prepared candidates
-> deduplicate physical nodes
-> one global Valhalla matrix
-> safety buffer
-> feasibility pruning
-> sparse arc graph N x K
```

## Port và adapter

Thay `RoutingProvider.travel_minutes(origin, destination)` bằng hai capability:

```text
RoutingMatrixProvider.matrix(locations, profile) -> TravelMatrix
RouteDetailProvider.route(legs, profile) -> RouteDetails
```

`ports.py` chỉ định nghĩa interface và model trung lập. Adapter Valhalla nằm
trong:

```text
adapters/valhalla.py
```

Node/service không gọi HTTP Valhalla trực tiếp. Dùng `httpx.AsyncClient`,
timeout và dependency injection. Matrix adapter phải trả:

```text
duration_seconds[from][to]
distance_meters[from][to]
reachable[from][to]
provider_version/cache_key metadata
```

Provider error phải phân biệt:

```text
matrix_timeout
matrix_provider_error
matrix_invalid_response
unreachable_pair
```

## Deduplicate physical nodes

Mỗi candidate vẫn là một solver node, nhưng matrix chỉ cần unique physical
locations.

Khóa deduplicate ưu tiên:

```text
placeId khi cùng ID
fallback: latitude/longitude làm tròn theo precision cấu hình
```

Kết quả:

```text
candidate_to_matrix_node[candidate_id]
matrix_node_to_candidates[matrix_node]
```

Hai candidate cùng physical node có travel time 0 nhưng vẫn có duration riêng;
không merge solver activity.

## Global matrix

Gọi một request cho:

```text
unique coordinates của valid places + valid food
```

Profile ban đầu là driving/auto. Matrix có hướng, không giả định:

```text
time[A][B] == time[B][A]
```

Không gọi route geometry cho toàn bộ cặp. Geometry chỉ lấy sau solver cho
selected arcs.

## Safety travel time

Chuyển giây thành phút và thêm buffer:

```text
rawMinutes = ceil(durationSeconds / 60)
safeMinutes = max(rawMinutes + 5, ceil(rawMinutes * 1.15))
```

Giữ cả raw và safe value để audit. Hard constraint dùng safe value;
`travelTimeCost` có thể dùng raw hoặc safe nhưng phải thống nhất trong config.

Unreachable pair không có arc. Nếu priority candidate bị cô lập hoàn toàn,
trả structured warning thay vì thay bằng khoảng cách ước lượng.

## Kiểm tra arc khả thi

Arc `i -> j` chỉ là candidate nếu tồn tại ít nhất một ngày chung sao cho:

```text
earliestEnd(i, day) + safeTravel(i, j) <= latestStart(j, day)
```

Với meal, phải kiểm tra meal window tương ứng. Kiểm tra này chỉ loại arc
chắc chắn bất khả thi; CP-SAT vẫn quyết định giờ cụ thể.

## Sparse graph N x K

Không tạo full `N x N x days`. Với mỗi node `i`:

1. Lọc reachable và time-feasible neighbors.
2. Xếp theo safe travel time, sau đó ID để deterministic.
3. Giữ `K=12` neighbors cơ bản.
4. Union thêm forced arcs.

Forced arcs:

```text
relationship target
arc cần để kết nối user_input/url
food khả thi cho meal kế tiếp
bridge arc giữa geographic clusters
```

Priority không có nghĩa là nối mỗi priority node với mọi node. Chỉ bổ sung
arc khi node priority thiếu incoming/outgoing path khả thi.

## Bảo đảm graph không bị đứt

Sau pruning, kiểm tra theo từng ngày:

```text
mỗi feasible node có ít nhất một incoming và outgoing arc
meal nodes có thể nối với activity trước/sau
priority nodes không bị cô lập do K quá nhỏ
```

Thêm bridge bằng nearest cross-component arcs cho tới khi candidate graph có
thể tạo một route. Không thêm unreachable arc.

Adaptive policy:

```text
solve K=12
model infeasible do graph sparsity -> rebuild K=20
vẫn infeasible -> expand riêng isolated/priority nodes
```

Cần phân biệt infeasible do sparse graph với infeasible do budget/opening. Chỉ
retry K khi diagnostics cho thấy thiếu connectivity.

## Virtual start/end

Input chưa có accommodation. Mỗi ngày dùng virtual start/end nội bộ:

```text
VIRTUAL_START[d] -> first stop -> ... -> last stop -> VIRTUAL_END[d]
```

Hai virtual leg có travel time/cost 0 và không xuất hiện trong itinerary. Sau
này có accommodation chỉ cần thay bằng matrix nodes thật.

## Transport cost

Matrix cung cấp distance, không tự biết giá di chuyển. Port trả riêng giá ban
ngày và phụ phí ban đêm, đều theo một người:

```text
TransportCostEstimator.estimate(distanceMeters, profile, people)
-> (daytimeCostPerPerson, lateNightSurchargePerPerson)
```

Implementation hiện tại là `XanhSmTransportCostEstimator`, dựa trên bảng giá
Green SM Car công khai cho Hà Nội được kiểm tra ngày 2026-08-13:

```text
2 km đầu:                 30.500 VND/xe
trên 2 đến 12 km:         14.700 VND/km
trên 12 đến 25 km:        13.800 VND/km
từ km 26:                 11.900 VND/km
phụ phí 22:00-06:00:      20.000 VND/xe
planning buffer:          15%
capacity mặc định:        4 người/xe
```

Nguồn: [Green SM - bảng giá Hà Nội](https://www.greensm.com/vn-vi/news/cach-dat-xe-taxi-xanh-sm-nhanh-chong-tien-loi).
Không tính khuyến mãi. Số xe là `ceil(people / 4)` và kết quả được chia lại
cho `people` để budget vẫn là budget/người. Phase 3 giữ riêng phụ phí đêm vì
chỉ Phase 4 mới biết arc được dùng vào giờ nào. Fare policy có version để cập
nhật/regression test khi hãng đổi giá.

Production không được âm thầm coi transport cost là 0 nếu hard budget bao gồm
transport.

## Cache

Cache matrix theo:

```text
routing profile
ordered canonical physical-node keys
Valhalla graph/version namespace
safety-buffer policy version
```

Phase đầu có thể dùng in-memory bounded cache. Durable cache chỉ thêm sau khi
xác định ownership; Planner không tự tạo DB table trong phase này.

## File map triển khai

```text
ports.py                         matrix/detail/cost interfaces
routing_models.py                TravelMatrix, RouteDetail, SparseArc
routing.py                       dedup, buffer, feasibility, sparse graph
adapters/valhalla.py             HTTP adapter
adapters/in_memory_matrix.py     deterministic tests
adapters/transport_cost.py       policy giá theo distance được inject
tests/test_routing_matrix.py
tests/test_sparse_arcs.py
tests/test_valhalla_adapter.py
```

## Acceptance criteria

- Matrix chỉ gọi một lần cho một planning request cache miss.
- A->B và B->A được giữ riêng.
- Candidate trùng physical location không làm phình matrix.
- Sparse graph trung bình gần `N x K`, không `N x N`.
- Relationship/priority node không bị cô lập do pruning.
- Unreachable pair không bị thay bằng estimated travel giả.
- Virtual nodes không xuất hiện trong output.
