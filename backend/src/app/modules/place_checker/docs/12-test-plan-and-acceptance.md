# Task 12: Test plan và acceptance

Cập nhật lần cuối: 2026-08-18

## Mục tiêu

Xác minh PlaceChecker end-to-end và khóa boundary với Explorer, Knowledge Graph,
external adapter và downstream planning.

## Các lớp test

- Unit: validation, normalization, policy, budget, gap, scoring và reranking.
- Contract: parse input/output, alias, enum và forbidden field.
- Adapter: KG, internal search, external search và promotion outbox.
- Integration: Explorer -> PlaceChecker -> planning projection.
- Failure: ambiguity, malformed evidence, stale data, timeout và partial output.

## Scenario bắt buộc

1. Parse canonical Hanoi input.
2. Reject ADM rỗng.
3. Resolve alias Hanoi thành canonical ADM.
4. Trả clarification khi ADM ambiguous.
5. Resolve exact KG place.
6. Không tự động fuzzy match tại threshold hoặc margin thấp.
7. Lexical similarity xử lý khác dấu, typo và alias.
8. Semantic/vector similarity trả top-K khi shared provider contract hỗ trợ;
   scenario này chưa thuộc acceptance của Checkpoint 2 hiện tại.
9. Semantic score cao nhưng sai ADM không được verify.
10. Giữ direct-user place unresolved.
11. Reject optional place ngoài destination.
12. Merge input và URL evidence.
13. Normalize URL note null.
14. Bảo toàn STT/OCR conflict.
15. Dedupe không làm mất provenance.
16. Resolve `pho` thành venue và alternatives.
17. Giữ weak item venue ở `partially_resolved`, không tự chọn.
18. Special experience chỉ tham chiếu canonical anchor place.
19. Tạo gap cho item unresolved.
20. Giữ low budget ở relative mode, không tạo target amount.
21. Giữ unknown cost trong rich output nhưng chiếu TravelPlace thiếu giá thành
    `0 VND` ở Planner output; venue và accommodation vẫn yêu cầu giá.
22. Báo mandatory capacity overload nhưng không remove.
23. Reject hoặc rerank optional nightlife.
24. Giữ nightlife user yêu cầu trực tiếp kèm warning.
25. Unknown opening hours thành conditional, không thành closed.
26. Direct-user closed thành blocked; optional closed thành rejected.
27. Giữ external result một nguồn ở provisional.
28. Verify external result được corroborate và enqueue promotion.
29. Bỏ qua external search khi KG đã đủ.
30. Trả partial output sau provider timeout.
31. Reject day/route field khỏi PlaceChecker output.
32. Chỉ project planner-ready và conditional place xuống downstream.
33. Travel reserve là quota mềm; thiếu reserve không block nếu hard meal pool
    vẫn unique match được mọi slot `day × breakfast/lunch/dinner`; thiếu hard
    slot phải block trước Planner dù tổng số Restaurant đã bằng `days * 3`.
33a. Travel reserve đủ dữ liệu phải giữ coverage mềm tối thiểu 6/20
     `Special_Experience` và 4/20 popular; thiếu bucket phải fallback đủ pool.
34. TravelPlace thiếu Restaurant `special_near` không block nếu general food
    pool đã qua eligibility filter vẫn đủ hard minimum.
35. Restaurant đã có trong food pool vẫn được tính paired theo anchor
    relationship dù priority hiện tại không phải `special_near`.
36. Food candidate được dedup và kiểm tra tọa độ, duration, giá, opening/meal
    window trước selection; candidate không đủ dữ liệu không được báo selected.
37. Query gần dùng khoảng cách tọa độ tối đa 5 km; cạnh `Special_Near` chỉ là
    evidence và OfferItem/SpecialExperience được đọc độc lập.
38. Restaurant xuất hiện cạnh nhiều anchor chỉ tạo một food candidate, nhưng
    giữ toàn bộ anchor relationships và provenance.
39. General ADM chỉ được query khi hard hoặc reserve unique matching còn thiếu,
    chỉ nhận meal type thiếu và loại Restaurant ID đã thấy.
40. Matching chạy lại sau general fallback; reserve matching không được dùng
    Restaurant đã nằm trong hard matching và compact output phải gửi cả hai
    assignment cùng missing slots sang Planner.

## Tiêu chí nghiệm thu

- Mọi planner-eligible place có canonical identity, tọa độ, verification,
  duration, cost profile, provenance và lifecycle state.
- Mọi direct-user candidate có kết quả rõ ràng và không bị score-drop.
- Place resolution và item resolution là hai flow riêng.
- Special experience tham chiếu Place nhưng không phải chính Place entity.
- Budget tách mandatory/optional và known/estimated/unknown cost.
- Gap analysis vẫn đa chiều; boundary Planner áp hard pool quota riêng theo số
  ngày sau verification và metadata filtering.
- KG đứng trước internal và external retrieval.
- Một external source không thể tạo planner eligibility.
- Promotion chạy async và idempotent.
- Lỗi một place hoặc provider không làm crash toàn bộ check.
- Output không chứa day allocation, route order hoặc final timeline.
- Focused, integration và acceptance test đều pass.

## Điều kiện hoàn thành cuối cùng

Tất cả Definition of Done trước đó được đáp ứng, scenario bắt buộc pass trong
CI, contract và architecture document khớp runtime behavior, và có thể bật
PlaceChecker mà không thay đổi ownership boundary của FinalItineraryPlanner.

## Kết quả Checkpoint 7

Test được đặt cùng module và chia theo contract, trip context, resolution,
evidence, item, evaluation, aggregate analysis, retrieval/promotion,
scoring/reranking, performance/resilience và pipeline output/projection.

Các test pipeline bổ sung xác nhận:

- input canonical chạy xuyên suốt thành rich output;
- resolved item và optional candidate còn provenance;
- projection không chứa day, route order hoặc travel leg;
- cache không gọi provider lặp lại và metadata chỉ query ID còn thiếu;
- concurrency bound được giữ;
- external call budget tối đa hai source;
- correlation/phase/tool metadata và metrics được tạo;
- PlaceChecker pipeline chạy được như một LangGraph subgraph độc lập.

Scenario semantic/vector chỉ được bật acceptance khi shared search provider thật
trả `semanticSimilarity`; hiện vẫn giữ đúng trạng thái chưa triển khai. Durable
promotion outbox và production provider là điều kiện triển khai hạ tầng, không
phải behavior giả lập trong acceptance suite.
