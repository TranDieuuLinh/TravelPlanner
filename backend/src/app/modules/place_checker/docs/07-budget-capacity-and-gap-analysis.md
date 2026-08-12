# Task 07: Phân tích budget, capacity, coverage và gap

## Mục tiêu

Đánh giá toàn bộ candidate set bằng amount, duration và metadata thực tế thay
vì dùng quy tắc số địa điểm cố định mỗi ngày.

## Phụ thuộc

Task 05-06. Input là `PlaceEvaluationBatch`, `ItemResolutionBatch` và
`TripEvaluationContext`. Task này không gọi search provider, không tạo place và
không thay đổi lifecycle state của từng place.

## Output

`TripAggregateAnalysis` gồm:

- `budget`: mandatory, optional và total cost;
- `capacity`: available/load minutes và geographic overhead;
- `coverage`: category, item, food, experience và time hint coverage;
- `gaps`: danh sách gap máy đọc được.

## Budget analysis

Mandatory và optional được báo riêng. Direct-user place là mandatory. URL,
item-resolved và system candidate là non-mandatory; optional đã `rejected`
không được tính vào budget dự kiến. Item-selected venue được tính một lần theo
canonical ID.

Mỗi group giữ:

- số place;
- số place có amount range đầy đủ;
- số place thiếu amount/currency;
- minimum/typical/maximum subtotal đã biết;
- currency và cờ `complete`;
- phân bố `free/low/medium/high/premium/unknown`.

`free` là tín hiệu rõ nên được tính amount 0. `unknown` không bao giờ được đổi
thành 0. Các currency khác nhau không được cộng chung.

### Target amount

- known minimum lớn hơn target -> `over`;
- complete maximum không vượt target -> `within`;
- complete range cắt qua target -> `at_risk`;
- range chưa complete và chưa chứng minh over -> `unknown`.

### Relative level

Không sinh target amount giả. Với `low`, medium/high/premium tier tạo
`at_risk`; với `medium`, high/premium tạo `at_risk`; toàn bộ tier unknown tạo
`unknown`. Có cả known tier và unknown tier tạo `at_risk`.

## Capacity analysis

Load được tách thành:

- `mandatory`: direct-user place;
- `preferred`: URL place và selected item venue;
- `optional`: system suggestion và optional khác;
- `total`.

Mỗi group giữ known/unknown duration count và tổng minimum/typical/maximum
minutes. Mandatory bị overload vẫn được giữ và tạo warning; service không tự
remove place.

Status:

- `overloaded`: known minimum/typical load vượt maximum capacity;
- `unknown`: có place nhưng không có typical duration nào;
- `at_risk`: còn unknown duration hoặc utilization vượt typical capacity;
- `underloaded`: typical utilization dưới 60%;
- `balanced`: utilization từ 60% đến 100%.

## Geographic overhead

Không chạy distance matrix N×N. Service tính tâm tọa độ, bán kính lớn nhất và
phân loại coarse spread:

- bán kính không quá 2 km: `compact`, 15 phút/chuyển tiếp;
- không quá 8 km: `moderate`, 30 phút/chuyển tiếp;
- lớn hơn 8 km: `dispersed`, 45 phút/chuyển tiếp;
- dưới hai tọa độ: `unknown`, không tự tạo overhead.

Đây chỉ là reserve phút thô cho capacity; route thật thuộc Final Planner.

## Coverage

Coverage chỉ nhìn place `planner_ready/conditional` và item `resolved`. Output
giữ category distribution, số item resolved/unresolved, food coverage,
experience coverage và source time hints.

`sufficient` yêu cầu có planner-eligible place, food, experience và không còn
item unresolved. Có một phần dữ liệu trả `partial`; không có candidate phù hợp
trả `insufficient`.

## Gap types

Hỗ trợ:

- mandatory identity/metadata;
- trip capacity;
- food và experience coverage;
- time-of-day conflict;
- budget;
- diversity;
- geographic balance;
- people/accessibility;
- data quality;
- destination compatibility.

Mỗi gap có ID ổn định, type, severity, trigger, suggested action, related place
IDs, related item indexes, resolved place IDs và status. Checkpoint 4 chỉ phát
hiện gap nên gap mới mặc định `open`; không tự đánh dấu resolved và không tự tạo
mandatory suggestion.

## Test và điều kiện hoàn thành

Test gồm target within/at-risk/over, relative low budget, unknown khác free,
mandatory/optional split, overload, underload theo phút, unknown duration,
coarse geographic spread, food/diversity/people/data-quality/time/destination
gap và unresolved item linkage.

Hoàn thành khi aggregate output deterministic, không chứa day allocation/route
order và không gọi retrieval provider.
