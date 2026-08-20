# Hướng dẫn triển khai PlaceChecker

Cập nhật lần cuối: 2026-08-20.

Thư mục này chứa kế hoạch triển khai stage PlaceChecker. Các module Python
production sẽ được thêm bên cạnh `docs/` khi từng task được thực hiện.

## Vị trí trong runtime

```text
Explorer
  -> ExplorerHandoffProjector
  -> PlaceChecker
  -> TripThemePlanner
  -> PlaceSelector
  -> Làm giàu timeline và route
  -> OverallChecker
```

PlaceChecker phân giải, xác minh, làm giàu và đánh giá candidate. Module không
phân bổ ngày, chọn khung giờ chính xác, tối ưu thứ tự route hoặc tạo itinerary.

## Cấu trúc source

Các boundary ổn định của module nằm ngay tại root: `public.py`, `contract.py`,
`ports.py`, `graph.py`, `pipeline.py`, `service.py` và các output contract.
Business logic được nhóm theo capability để tránh một thư mục phẳng quá lớn:

```text
place_checker/
├── analysis/       # budget, capacity, coverage và gap
├── evaluation/     # rule đánh giá, avoid và price policy
├── resolution/     # identity, item resolution và evidence enrichment
├── retrieval/      # query, verification, promotion và projection
├── scoring/        # scoring, reputation và reranking
├── selection/      # activity/style/pool; food nằm trong selection/food
├── planning/       # compact projection sang Planner
├── adapters/       # provider implementation của riêng PlaceChecker
└── tests/          # test của module
```

Module khác vẫn chỉ import contract được hỗ trợ qua `public.py`; các package
con chỉ là implementation detail của PlaceChecker.

PostgreSQL adapter đọc quan hệ Knowledge Graph theo ngữ nghĩa hiện hành:
`Special_Near` giữa các place, `Special_Experience` từ ADM tới place hoặc
`FoodItem`, `Offer_Item` và `Has_Style` từ place tới thuộc tính. Evidence quan hệ giữ trạng
thái, nguồn, confidence/priority và khoảng cách để phục vụ audit và scoring.

Nhánh food dùng toàn bộ `TravelPlace` và `Entertainment` đủ điều kiện, có tọa
độ trong pool cuối làm anchor thật. Một query PostgreSQL duy nhất trả cả quán
trong phạm vi 5 km và lựa chọn toàn ADM; `Special_Near`,
`Special_Experience -> FoodItem` và `Offer_Item -> FoodItem` là các signal cùng
một result set. Selector hard-filter avoid/eligibility, ưu tiên short
preference, cân bằng `FoodItem`, dedup restaurant toàn cục, kiểm tra đủ
breakfast/lunch/dinner cho từng ngày và giữ quan hệ tới mọi anchor mà quán có
thể phục vụ. `Has_Style` không tạo FoodItem, tag hoặc diversity bucket.
PostgreSQL adapter chỉ đọc quan hệ;
module không sở hữu migration Knowledge Graph. Công thức Bayesian nằm trong
`shared/tools/bayesian_rating.py`. PlaceChecker benchmark `rating` và
`reviewCount` riêng theo từng category; TravelPlace có hệ số cao nhất,
Restaurant ở mức trung bình, còn DrinkDessert/Entertainment chỉ là tín hiệu
phụ để review volume của quán ăn không lấn át địa điểm tham quan.

Planner projection chọn đúng một source note cho mỗi candidate: `urlNotes`
được ưu tiên; nếu không có thì dùng `description` và `url_google_map` đọc từ
Knowledge Graph làm Google/KG fallback. Output là object
`notes={text,sourceType,sourceUrl}`; ghi chú cá nhân không thuộc Place Checker.

Candidate pool gửi sang Planner có quota độc lập: 12 `TravelPlace`/ngày,
6 `Restaurant`/ngày, 2 `Entertainment`/ngày, 3 `DrinkDessert`/ngày và tối đa
3 `Accommodation` cho toàn chuyến. Entertainment do hệ
thống gợi ý phải đạt Bayesian-adjusted rating tối thiểu 4,2/5; input trực tiếp
và URL luôn được giữ. Candidate cửa hàng/dịch vụ thương mại như clothing,
souvenir, ceramic shop hoặc event planner không được dùng làm Entertainment du
lịch chỉ vì rating cao. DrinkDessert cũng phải có tín hiệu cafe/tea/bakery/
dessert/bar/lounge thật; quán ăn có note món đặc trưng không được đi nhầm nhánh.
Entertainment hệ thống phải có window giao buổi tối từ 18:00; DrinkDessert có
window ban ngày từ 07:00 đến 18:00. Hai quota được chọn riêng rồi mới gộp vào
`entertainment[]` với `entityType`, và mọi pool dùng chung dedup ID. Chỉ candidate vượt đủ
verification, metadata và compact-output policy mới được tính. Chỉ thiếu hard
breakfast/lunch/dinner feasibility mới làm kết quả `blocked`; thiếu reserve
TravelPlace hoặc Restaurant target chỉ tạo warning và vẫn cho Planner tự chọn.
Thiếu relationship gần cũng chỉ tạo warning vì Planner vẫn có thể dùng general food pool theo route. Compact
output gửi cả `foodCoverage` gồm hard/reserve assignments và missing slots để
Planner biết feasibility đã được kiểm tra trước.

Recovery pool chỉ chạy khi pool hiện có thiếu target và tạo tối đa một query
catalog cho mỗi loại: TravelPlace, Restaurant, DrinkDessert, Entertainment và
Accommodation. Các kết quả được enrich metadata theo batch rồi lọc avoid,
eligibility và rank theo short preference trong cùng lượt. `Special_Experience`,
tag property trực tiếp, `Offer_Item`, rating/review và metadata quality là signal
của cùng candidate set; không có waterfall query theo theme. Google Maps không
được dùng để lấp pool. Nếu tên/tag cho
thấy rõ venue giải trí/dịch vụ/retail như music box, karaoke, golf, bi-a,
studio, massage/trị liệu hoặc store/souvenir, runtime sửa category `TravelPlace`
sai thành `Entertainment` trước khi chia quota.
Candidate có provenance `pool_category=shopping` cũng đi vào leisure pool thay
vì được tính là landmark, kể cả tên thương hiệu không chứa từ retail rõ ràng.
Compact projection còn đọc provider note để nhận các source category như art
supply store, photo booth, garden center và plant service; các venue thương mại
này cũng đi vào leisure pool thay vì TravelPlace.
Ngược lại, tên món/quán ăn rõ ràng sửa source `cafe/entertainment` sai về
`Restaurant` trước scoring và compact projection.
`pool_category` chỉ lưu provenance và không tạo diversity.
PostgreSQL adapter ánh xạ `entity_type` thành `category` canonical; các bước
downstream chuẩn hóa `category` trước khi đưa sang Planner. Các alias như
`cafe`, `coffee` và `DrinkDessert` đi vào pool `drink_dessert`, không rơi vào
TravelPlace. `place_id` không bị đổi theo category.
`Special_Experience` trạng thái `pending` nhận trust thấp hơn; đây không phải
phân ngày hoặc quyết định itinerary.

Compact output chỉ dùng tag hợp lệ từ `auto-attach/tags-auto.yml`; `Has_Style`
không được chiếu thành tag/style semantic. Output vẫn gửi
`audience={adultOnly,kidSuitable}`. Trip gửi `party={adults,kids}` cùng
`preferences={tags,avoidTags,styles}`; Planner tiếp tục quyết định eligibility,
preference, style và tag-repetition trong lịch cuối.

## Input từ Explorer

```json
{
  "inputADM": "Hanoi",
  "places": [],
  "inputItems": [],
  "days": 4,
  "budget": {
    "amountPerPerson": 2500000,
    "currency": "VND",
    "level": "low"
  },
  "people": {
    "adults": 1,
    "children": 0,
    "infants": 0
  },
  "shortPreferences": [],
  "shortAvoids": ["nightlife"],
  "specialNotes": []
}
```

Địa điểm lấy từ URL được biểu diễn bằng phần tử trong
`places[].sourcePlaces[]` có `evidenceType="url"` và `sourceUrl`. Note đã liên
kết nằm tại `sourcePlaces[].urlNotes[]` và chỉ chứa `summary`; không có
top-level `urlNotes`. Boundary không chuyển `tags`, `confidence`, `origin`,
`evidence`, `observedAt`, `sourceType`, extractor/model version hoặc cache
metadata. Direct PlaceChecker payload tự gửi extra key sẽ thành
candidate-level validation issue.

`ExplorerHandoffProjector` là boundary duy nhất của root: merge Conversation
Memory theo precedence, resolve tag bằng `auto-attach/tags-auto.yml`, validate
final-dedupe place và gộp source evidence, rồi tạo `PlaceCheckerInput`. Root
không gate theo `ready`/`partial` hoặc `input_ADM`; thiếu destination được trả
dạng `blocked`, còn Explorer/provider/runtime failure được trả dạng `error` có
cấu trúc.

Operation sửa trip context và phần việc Supervisor được mô tả tại
[`Explorer Supervisor handoff`](../explorer/docs/supervisor-trip-context-handoff.md).

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
  search thống nhất name/alias/address trong ADM trên cả năm entity type và
  chọn catalog top-1. Chỉ khi catalog trả zero row mới gọi Google Maps; lỗi
  catalog hoặc một row không đủ điều kiện không kích hoạt external.
- Runtime PostgreSQL có `PostgresPlaceCatalog` đọc bốn bảng Knowledge Graph.
  Named-place query không đọc relation discovery. Requirement query dùng
  `pg_trgm`, direct tags và relationship signal, giới hạn top-K trước khi map
  metadata. Đây là nguồn đọc, không sở hữu hay ghi dữ liệu Knowledge.
- Semantic/vector chưa nằm trong contract thực tế của shared tool. Chỉ được bật
  sau khi provider trả component `semanticSimilarity` có nguồn rõ ràng.
- Checkpoint 3 đã có item resolution qua mode `requirement`, special experience
  projection và đánh giá từng place thành
  `planner_ready/conditional/blocked/rejected`.
- Checkpoint 4 đã có aggregate budget, duration capacity, coarse geographic
  overhead, coverage và multi-dimensional gap analysis.
- Checkpoint 5 đã có targeted retrieval theo gap, adapter gọi
  `shared/tools/search_places`, chặn candidate retrieval provisional khỏi
  Planner và không cấu hình external source cho pool runtime. Identity từ
  URL/input vẫn giữ provenance và được tự chọn theo catalog top-1 đúng ADM;
  address hint được gửi vào shared search để ưu tiên ranking. Match này đi tiếp
  dưới dạng `provisional`/conditional kèm constraint bắt buộc xác minh, không mở
  branch Top-K ở frontend.
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
