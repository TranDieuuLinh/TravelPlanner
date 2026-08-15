# Phase 3: Valhalla matrix và sparse arcs

Trạng thái: đã triển khai routing ports/models, Valhalla HTTP adapter, route
detail adapter, straight-line fallback, in-memory bounded cache, coordinate
deduplication, directed global matrix, safe travel values, time-feasibility
pruning, sparse/forced/bridge arcs và virtual START/END. Graph đã có node
`build_travel_matrix` qua dependency injection. Nếu Valhalla không sẵn sàng,
Planner dùng fallback đường chim bay có warning rõ ràng.

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

`ports.py` chỉ định nghĩa interface và model trung lập. Adapter Valhalla và
fallback đường chim bay nằm trong:

```text
adapters/valhalla.py
adapters/straight_line.py
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

Fallback đường chim bay dùng khoảng cách Haversine, tốc độ profile cố định và
polyline6 chỉ gồm điểm đầu/cuối. Đây là ước tính để planner tiếp tục chạy,
không phải quãng đường hoặc thời gian theo đường thật; output luôn có warning.

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
3. Giữ `K=10` neighbors cơ bản để giảm số arc/biến CP-SAT.
4. Union thêm forced arcs.

Forced arcs:

```text
relationship target
arc cần để kết nối user_input/url
food khả thi cho meal kế tiếp
bridge arc giữa geographic clusters
```

Priority không có nghĩa là nối mỗi priority node với mọi node. Chỉ bổ sung
arc khi node priority thiếu incoming/outgoing path khả thi. Sau khi giảm
`K=10`, policy cũng bổ sung nearest incoming/outgoing cho mọi candidate khả thi
nếu pruning làm candidate đó chỉ còn một chiều; việc này giữ candidate
preference/source-mix trong miền lựa chọn mà không khôi phục full graph.

## Bảo đảm graph không bị đứt

Sau pruning, kiểm tra theo từng ngày:

```text
mỗi feasible node có ít nhất một incoming và outgoing arc
meal nodes có thể nối với activity trước/sau
priority nodes không bị cô lập do K quá nhỏ
```

Thêm bridge bằng nearest cross-component arcs cho tới khi candidate graph có
thể tạo một route. Không thêm unreachable arc.

Khoảng cách để chọn neighbor là `safeTravelMinutes` có hướng từ global
Valhalla matrix, đã gồm routing buffer. Khi bằng nhau mới tie-break bằng ID để
giữ deterministic. Không dùng khoảng cách đường chim bay khi matrix Valhalla
khả dụng.

Adaptive policy mục tiêu:

```text
solve K=10
model infeasible do graph sparsity -> rebuild K=20
vẫn infeasible -> expand riêng isolated/priority nodes
```

Cần phân biệt infeasible do sparse graph với infeasible do budget/opening. Chỉ
retry K khi diagnostics cho thấy thiếu connectivity.

## Virtual start/end

Accommodation hiện dùng cho cost và output, chưa được dùng làm routing anchor.
Mỗi ngày vẫn dùng virtual start/end nội bộ:

```text
VIRTUAL_START[d] -> first stop -> ... -> last stop -> VIRTUAL_END[d]
```

Hai virtual leg có travel time/cost 0 và không xuất hiện trong itinerary. Bước
sau có thể dùng tọa độ accommodation làm matrix node thật.

## Transport cost

Matrix cung cấp distance, không tự biết giá di chuyển. Port trả riêng giá ban
ngày và phụ phí ban đêm, đều theo một người:

```text
TransportCostEstimator.estimate(distanceMeters, profile, people)
-> (daytimeCostPerPerson, lateNightSurchargePerPerson)
```

Implementation hiện tại là shared `XanhSmTransportCostEstimator` tại
`app/shared/tools/transport_cost.py`, dựa trên bảng giá
Green SM Car công khai cho Hà Nội được kiểm tra ngày 2026-08-14:

```text
2 km đầu:                 30.500 VND/xe
trên 2 đến 12 km:         14.700 VND/km
trên 12 đến 25 km:        13.800 VND/km
từ km 26:                 11.900 VND/km
phụ phí 22:00-06:00:      20.000 VND/xe
planning buffer:          15%
capacity mặc định:        4 người/xe
```

Nguồn: [Green SM - bảng giá Hà Nội](https://www.greensm.com/vn-vi/news/bang-gia-xe-taxi-ha-noi).
Không tính khuyến mãi. Số xe là `ceil(people / 4)` và kết quả được chia lại
cho `people` để budget vẫn là budget/người. Phase 3 giữ riêng phụ phí đêm vì
chỉ Phase 4 mới biết arc được dùng vào giờ nào. Fare estimate mang provider,
market, currency và version để city-cost estimation tái sử dụng cùng nguồn.
Fare policy có version để cập nhật/regression test khi hãng đổi giá.

Phase 5 dùng shared `DailyCostCalculator` tạo breakdown/người/ngày. Food và
activities lấy từ stop đã chọn, local transport lấy từ route; accommodation
lấy từ `pricePerNight` đã chọn và số phòng suy ra, còn misc bằng 0 khi chưa có
dữ liệu.

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
ports.py                         matrix/detail interfaces
routing_models.py                TravelMatrix, RouteDetail, SparseArc
routing.py                       dedup, buffer, feasibility, sparse graph
adapters/valhalla.py             HTTP adapter
adapters/in_memory_matrix.py     deterministic tests
shared/tools/transport_cost.py   policy giá theo distance dùng chung
shared/tools/daily_cost.py       cộng breakdown chi phí/người/ngày
adapters/transport_cost.py       compatibility import cho caller cũ
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
