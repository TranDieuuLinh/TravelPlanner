# Hướng dẫn triển khai PlaceChecker

Cập nhật lần cuối: 2026-08-18.

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
PostgreSQL adapter đọc quan hệ Knowledge Graph theo ngữ nghĩa hiện hành:
`Special_Near` giữa các place, `Special_Experience` từ ADM tới place hoặc
`FoodItem`, `Offer_Item` và `Has_Style` từ place tới thuộc tính. Evidence quan hệ giữ trạng
thái, nguồn, confidence/priority và khoảng cách để phục vụ audit và scoring.

Nhánh food bắt đầu từ sáu Style food/drink, lấy các `FoodItem`/`DrinkItem` qua
`Has_Style`, rồi truy ngược `Offer_Item` để tìm `Restaurant`/`DrinkDessert`
trong bán kính tối đa 5 km quanh TravelPlace anchor. Mỗi Style có target mềm
`2 × days`; selector ưu tiên Item và quán chưa dùng trong từng anchor region,
chỉ quay vòng Item sau khi lựa chọn khác đã cạn. `Special_Near` là evidence bổ
sung, không phải điều kiện vào query. Service vẫn loại metadata không dùng được,
dựng các slot `day × breakfast/lunch/dinner` và chạy unique bipartite matching.
Khi meal matching hoặc Style coverage còn thiếu, service query general ADM một
lần rồi chọn lại.
Hai matching không dùng chung Restaurant. PostgreSQL adapter chỉ đọc quan hệ;
module không sở hữu migration Knowledge Graph. Công thức Bayesian nằm trong
`shared/tools/bayesian_rating.py`. PlaceChecker benchmark `rating` và
`reviewCount` riêng theo từng category; TravelPlace có hệ số cao nhất,
Restaurant ở mức trung bình, còn DrinkDessert/Entertainment chỉ là tín hiệu
phụ để review volume của quán ăn không lấn át địa điểm tham quan.

Planner projection chọn đúng một source note cho mỗi candidate: `urlNotes`
được ưu tiên; nếu không có thì dùng `description` và `url_google_map` đọc từ
Knowledge Graph làm Google/KG fallback. Output là object
`notes={text,sourceType,sourceUrl}`; ghi chú cá nhân không thuộc Place Checker.

Candidate pool gửi sang Planner có quota độc lập: 22 TravelPlace/ngày,
16 Restaurant/ngày và 6 DrinkDessert/Entertainment/ngày. Entertainment do hệ
thống gợi ý phải đạt Bayesian-adjusted rating tối thiểu 4,2/5; input trực tiếp
và URL luôn được giữ. Compact pool chỉ giữ một Entertainment có thể xếp buổi
sáng trong mỗi năm ngày, còn DrinkDessert và Entertainment chỉ mở buổi
chiều/tối không chịu giới hạn sáng này. `22 TravelPlace/ngày` là target retrieval
để tạo nhiều phương án, không phải hard gate: compact handoff chỉ cần tối thiểu
8 TravelPlace/ngày trước khi gọi Planner. Food reserve
được over-fetch riêng để chứa `2 × days` candidate cho sáu Style. Chỉ candidate vượt đủ
verification, metadata và compact-output policy mới được tính. Thiếu hard
handoff pool làm kết quả `blocked`; root không tạo `planner_input`. Thiếu relationship gần
chỉ tạo warning vì Planner vẫn có thể dùng general food pool theo route. Compact
output gửi cả `foodCoverage` gồm hard/reserve assignments và missing slots để
Planner biết feasibility đã được kiểm tra trước.

TravelPlace reserve chạy query lõi riêng cho famous/must-see landmark và các
query khám phá độc lập cho culture, nature,
shopping, nightlife, workshop, performance, outdoor, family, special
experience và local activity. Đây là query intent, không phải theme của place.
Selection giữ một đại diện cho mỗi tag KG có ý nghĩa trước khi bù theo tỷ lệ
tham chiếu theo tỷ lệ 6/14 candidate có evidence `Special_Experience`,
4/14 candidate có Bayesian popularity signal và phần còn lại theo ranking.
Popular chỉ được tính khi có ít nhất 500 review và popularity score từ 0,70;
candidate vài trăm review không còn làm đầy bucket landmark. Nếu tên/tag cho
thấy rõ venue giải trí/dịch vụ/retail như music box, karaoke, golf, bi-a,
studio, massage/trị liệu hoặc store/souvenir, runtime sửa category `TravelPlace`
sai thành `Entertainment` trước khi chia quota.
Candidate có provenance `pool_category=shopping` cũng đi vào leisure pool thay
vì được tính là landmark, kể cả tên thương hiệu không chứa từ retail rõ ràng.
Ngược lại, tên món/quán ăn rõ ràng sửa source `cafe/entertainment` sai về
`Restaurant` trước scoring và compact projection.
Khi fill phần còn lại, selector ưu tiên tag ít xuất hiện và soft-cap một tag
rộng ở tối đa 3 candidate nếu còn tag khác để thay thế. `pool_category` chỉ lưu
provenance và không tạo diversity.
PostgreSQL adapter ánh xạ `entity_type` thành `category` canonical; các bước
downstream chuẩn hóa `category` trước khi đưa sang Planner. Các alias như
`cafe`, `coffee` và `DrinkDessert` đi vào pool `drink_dessert`, không rơi vào
TravelPlace. `place_id` không bị đổi theo category.
Query khám phá bắt buộc match relation/style term; một `Special_Experience`
không liên quan không được dùng để lấp mọi query.
`Special_Experience` trạng thái `pending` không được tính là special. Bucket
thiếu được pool khác bù; đây không phải phân ngày hoặc quyết định itinerary.

Compact output tách tag phẳng khỏi `styles` lấy từ `Has_Style` đã duyệt và gửi
`audience={adultOnly,kidSuitable}`. Trip gửi `party={adults,kids}` cùng
`preferences={tags,avoidTags,styles}`; Planner tiếp tục quyết định eligibility,
preference, style và tag-repetition trong lịch cuối.

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
được chuẩn hóa thành danh sách rỗng. Boundary giữ các provenance field của
Explorer gồm `platform`, `extractorVersion`, `modelVersion` và `cacheStatus`;
candidate không bị loại chỉ vì mang metadata nguồn này.

Explorer truyền JSON camelCase. Pydantic chấp nhận camelCase này và chuyển sang
snake_case trong Python; output JSON mẫu hiện dùng snake_case theo contract nội
bộ của pipeline.

Explorer public output còn mang `startDate` và `timezone`. Root orchestration
dùng hai field này khi gọi `PlaceCheckerPlannerOutputBuilder`; PlaceChecker
không tự suy đoán lại ngày bắt đầu.

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
- Runtime PostgreSQL có `PostgresPlaceCatalog` đọc bốn bảng Knowledge Graph.
  Candidate được tạo bằng exact/alias, `pg_trgm` similarity và quan hệ trực
  tiếp, giới hạn top-K trước khi map metadata; external fallback vẫn tách qua
  port của module. Đây là nguồn đọc, không sở hữu hay ghi dữ liệu Knowledge.
- Semantic/vector chưa nằm trong contract thực tế của shared tool. Chỉ được bật
  sau khi provider trả component `semanticSimilarity` có nguồn rõ ràng.
- Checkpoint 3 đã có item resolution qua mode `requirement`, special experience
  projection và đánh giá từng place thành
  `planner_ready/conditional/blocked/rejected`.
- Checkpoint 4 đã có aggregate budget, duration capacity, coarse geographic
  overhead, coverage và multi-dimensional gap analysis.
- Checkpoint 5 đã có targeted retrieval theo gap, adapter gọi
  `shared/tools/search_places`, xác minh KG/hai nguồn ngoài, chặn candidate
  retrieval provisional khỏi Planner. Identity điểm trung bình từ URL/input
  được giữ ở `provisional` khi có exact/alias, address hoặc semantic evidence
  mạnh; nó đi tiếp dưới dạng conditional kèm constraint bắt buộc xác minh.
  Promotion worker và outbox bộ nhớ dùng cho development/test.
- Checkpoint 5 đã có scoring giải thích được theo 10 thành phần, penalty có
  giới hạn và deterministic diversity reranking theo category, experience type
  và cụm tọa độ 2 km.
- Chưa có durable promotion outbox, provider external production hay workflow
  provider production. Những phần này không được xem là đã chạy production.
- Checkpoint 6 đã có `PlaceCheckerPipeline`, rich output V1, pipeline subgraph,
  projection Explorer legacy -> input canonical và projection riêng cho
  downstream. KG vẫn giữ unknown cost; riêng TravelPlace thiếu giá được compact
  projection thành `0 VND` để Planner không loại địa điểm. Food, entertainment
  và accommodation vẫn cần giá dùng được.
- Checkpoint 6 cũng có phase timing, correlation metadata, metrics port, cache
  wrapper và giới hạn concurrency/call budget. Root graph mặc định vẫn dùng
  compatibility graph cho đến khi production provider được cấu hình.
- Checkpoint 7 đã có unit, contract, adapter, resilience, pipeline và projection
  test. Acceptance hiện chạy cùng toàn bộ test của module.
