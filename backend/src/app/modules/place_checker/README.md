# Hướng dẫn triển khai PlaceChecker

Cập nhật lần cuối: 2026-08-11.

Thư mục này chứa kế hoạch triển khai stage PlaceChecker. Các module Python
production sẽ được thêm bên cạnh `docs/` khi từng task được thực hiện.

## Vị trí trong runtime

```text
Explorer
  -> PlaceChecker
  -> TripThemePlanner
  -> PlaceSelector
  -> Làm giàu timeline và route
  -> OverallChecker
```

PlaceChecker phân giải, xác minh, làm giàu và đánh giá candidate. Module không
phân bổ ngày, chọn khung giờ chính xác, tối ưu thứ tự route hoặc tạo itinerary.

## Input từ Explorer

```json
{
  "inputADM": "Hanoi",
  "places": [],
  "inputItems": [],
  "urlNotes": null,
  "days": 4,
  "budget": {
    "level": "low",
    "targetAmount": null,
    "currency": "VND",
    "source": "raw_prompt"
  },
  "people": {
    "adults": 1,
    "children": 0,
    "infants": 0
  },
  "shortPreferences": [],
  "shortAvoids": ["nightlife"]
}
```

Địa điểm lấy từ URL được biểu diễn bằng phần tử trong
`places[].sourcePlaces[]` có `origin` là `url`. `urlNotes` có thể là `null` và
được chuẩn hóa thành danh sách rỗng.

Explorer truyền JSON camelCase. Pydantic chấp nhận camelCase này và chuyển sang
snake_case trong Python; output JSON mẫu hiện dùng snake_case theo contract nội
bộ của pipeline.

## Thứ tự triển khai

| Milestone | Task | Điểm kiểm tra |
| --- | --- | --- |
| 1 | 01-02 | Parse contract và phân giải trip context |
| 2 | 03-04 | Phân giải, chống trùng và làm giàu địa điểm |
| 3 | 05-06 | Phân giải item và đánh giá từng địa điểm |
| 4 | 07 | Phân tích tổng budget, capacity, coverage và gap |
| 5 | 08-09 | Truy xuất, xác minh, chấm điểm và xếp hạng lại candidate tùy chọn |
| 6 | 10-11 | Tích hợp workflow và bổ sung kiểm soát vận hành |
| 7 | 12 | Vượt qua toàn bộ acceptance test |

Bắt đầu từ [requirement tổng thể](docs/00-overall-requirement.md). Mỗi tài liệu
task đều mô tả dependency, các bước triển khai, test và Definition of Done.
Tỷ lệ bốc pool theo buổi và sở thích được mô tả tại
[chính sách cho flow sau](docs/13-downstream-pool-selection-policy.md).

## Trạng thái triển khai

- Checkpoint 1 đã có contract, validation, chuẩn hóa input và phân giải ADM qua
  interface `AdmResolver`.
- Checkpoint 2 gọi trực tiếp `shared/tools/search_places/SearchPlacesTool` để
  nhận diện exact/alias/lexical, áp ngưỡng chấp nhận, chống trùng kết quả
  provider, giữ provenance và làm giàu metadata. External fallback luôn bị tắt
  tại checkpoint này.
- Adapter Knowledge Graph và kho metadata production chưa được nối. Checkpoint
  2 hiện cung cấp port để adapter thật triển khai và được kiểm thử bằng fake.
- Semantic/vector chưa nằm trong contract thực tế của shared tool. Chỉ được bật
  sau khi provider trả component `semanticSimilarity` có nguồn rõ ràng.
- Checkpoint 3 đã có item resolution qua mode `requirement`, special experience
  projection và đánh giá từng place thành
  `planner_ready/conditional/blocked/rejected`.
- Checkpoint 4 đã có aggregate budget, duration capacity, coarse geographic
  overhead, coverage và multi-dimensional gap analysis.
- Checkpoint 5 đã có targeted retrieval theo gap, adapter gọi
  `shared/tools/search_places`, xác minh KG/hai nguồn ngoài, chặn candidate
  provisional khỏi Planner, promotion worker và outbox bộ nhớ dùng cho
  development/test.
- Checkpoint 5 đã có scoring giải thích được theo 10 thành phần, penalty có
  giới hạn và deterministic diversity reranking theo category, experience type
  và cụm tọa độ 2 km.
- Chưa có durable promotion outbox, provider external production hay workflow
  provider production. Những phần này không được xem là đã chạy production.
- Checkpoint 6 đã có `PlaceCheckerPipeline`, rich output V1, pipeline subgraph,
  projection Explorer legacy -> input canonical và projection riêng cho
  downstream. Contract projection giữ unknown cost/duration thay vì ép thành 0.
- Checkpoint 6 cũng có phase timing, correlation metadata, metrics port, cache
  wrapper và giới hạn concurrency/call budget. Root graph mặc định vẫn dùng
  compatibility graph cho đến khi production provider được cấu hình.
- Checkpoint 7 đã có unit, contract, adapter, resilience, pipeline và projection
  test. Acceptance hiện chạy cùng toàn bộ test của module.
