# Requirement tổng thể của PlaceChecker

## Mục tiêu

PlaceChecker chuyển output của Explorer thành tập địa điểm và trải nghiệm có
nguồn, đủ an toàn để lập kế hoạch. Stage này bảo toàn ý định người dùng và
provenance, đồng thời thể hiện rõ mọi điểm chưa chắc chắn.

PlaceChecker phải trả lời bốn câu hỏi:

1. Mỗi mention đang nói tới canonical place nào?
2. Place đã được xác minh và có đủ dữ liệu để lập kế hoạch chưa?
3. Toàn bộ candidate set có khả thi với trip context không?
4. Gap nào cần tìm thêm dữ liệu, review hoặc chuyển thành constraint downstream?

## Ngoài phạm vi

PlaceChecker không được:

- phân bổ địa điểm vào ngày;
- chọn giờ ghé thăm chính xác;
- tính travel matrix cuối cùng hoặc thứ tự route;
- loại direct-user place vì ranking score;
- suy ra ngân sách tiền từ `low`, `medium` hoặc `high`;
- tự tạo place identity, tọa độ, giá hoặc opening hours.

## Mức ưu tiên nguồn và truy xuất

Thứ tự bảo vệ nguồn:

```text
direct_user -> url -> item_resolved -> system_suggested
```

Thứ tự truy xuất:

```text
Knowledge Graph -> internal normalized search -> external search
```

Trong bước phân giải identity, Knowledge Graph cần hỗ trợ nhiều loại
similarity theo thứ tự:

```text
exact name
-> verified alias
-> lexical similarity
-> semantic/vector similarity nếu có embedding
```

Checkpoint 2 hiện thực exact, alias và lexical similarity bằng
`shared/tools/search_places/SearchPlacesTool`. Semantic/vector là capability
mục tiêu, chưa được coi là đã triển khai cho tới khi shared provider contract
trả score semantic có provenance. PlaceChecker không duy trì một công thức
similarity riêng song song với shared tool.

Checkpoint 3 dùng mode `requirement` của cùng shared tool để phân giải
`input_items`, sau đó đánh giá từng place bằng deterministic policy. Phân tích
tổng budget, capacity, coverage và gap được thực hiện ở Checkpoint 4 mà không
gọi retrieval hoặc tạo place mới.

Similarity chỉ dùng để tạo và xếp hạng các match option, không tự chứng minh
candidate là đúng. Kết quả vẫn phải qua kiểm tra ADM, address, category, tọa độ
và ngưỡng confidence trước khi thành `verified`.

Direct-user place mặc định là mandatory và không được remove. URL place mặc
định là preferred. Item-resolved place là một phương án có thể thay thế để thực
hiện requirement của người dùng. System suggestion luôn là optional.

## State machine của Place

```text
received
  -> normalized
  -> resolving
      -> unresolved
      -> needs_review
      -> resolved
  -> enriched
      -> provisional
      -> verified_kg
      -> verified_external
  -> evaluated
      -> planner_ready
      -> conditional
      -> blocked
      -> rejected
```

Chỉ `planner_ready` và `conditional` mới đủ điều kiện chuyển sang downstream
planning. Place `conditional` luôn có warning hoặc planner constraint.
Direct-user candidate chỉ có thể kết thúc ở `planner_ready`, `conditional`,
`blocked` hoặc `unresolved`; không bao giờ bị reject âm thầm.

## Chính sách xác minh

- Match với canonical entity trong KG là `verified_kg`.
- Candidate từ một external source là `provisional`, mặc định không đủ điều kiện
  cho Planner.
- Canonical candidate tốt nhất từ URL/direct input đúng ADM, có stable identity
  và tọa độ được giữ là identity `provisional`; nó có thể đi vào Planner ở
  trạng thái `conditional` với constraint xác minh identity/chi nhánh.
- Hai external source độc lập đồng thuận về identity, destination, category và
  tọa độ có thể tạo `verified_external`.
- Các match xung đột hoặc quá sát nhau tạo `needs_review`.
- Entity external đã xác minh được đẩy vào async outbox để promote vào KG theo
  cách idempotent. Lỗi promotion không làm request planning thất bại.

## Luồng tổng thể

```text
validate input
-> chuẩn hóa ADM và trip context
-> chuẩn hóa place, item, note và evidence
-> phân giải canonical identity
-> merge evidence và chống trùng
-> làm giàu metadata
-> phân giải item requirement
-> đánh giá constraint và suitability
-> phân tích tổng duration, budget, geography và coverage
-> phát hiện gap
-> truy xuất và xác minh optional candidate có giới hạn
-> scoring và diversity reranking optional candidate
-> final validation
-> tạo output cho FinalItineraryPlanner
```

## Các nhóm trong production output

Contract cuối cùng gồm:

- `trip_context`;
- `checked_places` và `planner_eligible_place_ids`;
- `resolved_items` và `special_experiences`;
- `coverage_analysis`, `gap_analysis` và `budget_analysis`;
- `geographic_analysis`;
- `unresolved_entities`, warning và planner constraint;
- metadata thực thi và số lần gọi tool.

Mỗi checked place phải có identity, tọa độ, destination compatibility, source
tier, chính sách mandatory/removable, category, duration, cost, opening/time
constraint, suitability, verification, confidence, provenance, warning và state.

## Pseudocode

```text
check(input):
    validated = validate(input)
    context = build_trip_context(validated)
    candidates, items, notes = normalize(validated)
    identities = resolve_places_in_batches(candidates, context)
    places = merge_deduplicate_and_enrich(identities, notes)
    resolved_items = resolve_items(items, context)
    evaluate_places(places, context)
    analyses = analyze_budget_capacity_geography_and_coverage(places, context)
    gaps = detect_gaps(places, resolved_items, analyses)
    optional = retrieve_verify_and_rank_for_open_gaps(gaps, context)
    queue_verified_external_promotions(optional)
    return final_validate_and_build_output(...)
```

## Danh sách task

Task 01-12 là các checkpoint triển khai. Một task chỉ hoàn thành khi focused
test của task đó pass và output contract có thể được task tiếp theo sử dụng.
