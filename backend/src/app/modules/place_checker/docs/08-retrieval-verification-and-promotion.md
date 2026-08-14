# Task 08: Truy xuất, xác minh và promotion

## Mục tiêu

Truy xuất tập candidate có giới hạn cho từng open gap và xác lập trust state rõ
ràng trước khi chuyển sang downstream planning.

## Phụ thuộc

Task 07. Đây là task đầu tiên có thể cần migration cho promotion outbox.

## Chiến lược truy xuất

```text
relation-first KG query
-> relation query through the anchor's ADM
-> normalized internal search/cache
-> external source A
-> external source B khi cần corroboration
```

Không gọi external search khi kết quả KG/internal đã đủ giải quyết gap. Search
theo gap type, ADM, category/experience, budget tier, people policy và time
constraint liên quan. Keyword không phải nguồn ưu tiên; chỉ được dùng để lấp
phần thiếu sau khi đã lấy ứng viên có quan hệ.

Mỗi truy vấn pool nhận thêm `anchor_place_ids` của các địa điểm người dùng nhập
trực tiếp. Knowledge Graph chỉ dùng edge `Special_Near` để ưu tiên candidate
quanh điểm neo. Nếu điểm neo không có cạnh đủ trực tiếp, truy vấn mở rộng qua
ADM chứa điểm neo để đọc `Special_Experience` của khu vực. Candidate được gắn
nhãn như `relation:special_near`, `relation:area_special_experience` hoặc
`retrieval:keyword_fallback` để downstream giải thích được lý do chọn.

Thứ tự ưu tiên quan hệ là:

```text
Special_Near trực tiếp
-> Special_Experience từ ADM trong destination
-> Offer_Item/Has_Style của place
-> cùng cụm địa lý
-> keyword fallback
```

Khi pool có ít quan hệ, fallback vẫn được phép để đủ số lượng nhưng không được
giả dạng là candidate liên quan mạnh; candidate đó phải có nhãn fallback và
được trừ điểm ở bước ranking.

Với item như `pho`, truy vấn food được mở rộng thành `pho restaurant` và dùng
edge `Offer_Item` để khớp món. Với hoạt động, các edge `Special_Experience` và
`Has_Style` được đưa vào tags để nhận diện trải nghiệm và phong cách thay vì
chỉ dựa vào tên địa điểm.

PostgreSQL adapter duyệt cây `Located_In` đệ quy từ destination xuống các ADM
con, nên query ADM1 vẫn lấy được place gắn trực tiếp vào ADM2. Mỗi edge được
chuẩn hóa thành evidence gồm type, direction, scope, status, confidence,
priority, distance, source và source note. `Special_Experience` pending được
dùng mở rộng pool nhưng nhận score thấp và warning/penalty; nó không được diễn
giải thành recommendation đã review.

## Xác minh

- Kết quả link được KG: `verified_kg`.
- Một external source: `provisional`, chưa planner-eligible.
- Identity provisional có nguồn URL/direct input là trường hợp riêng: phải có
  canonical ID, tọa độ, đúng ADM, score/name score đạt ngưỡng và exact/alias,
  address hoặc semantic evidence mạnh; được giữ cho Planner dưới trạng thái
  conditional với constraint xác minh.
- Hai source độc lập đồng thuận về name, region, category và coordinates:
  `verified_external`.
- Source conflict đáng kể: `needs_review`.
- Provider popularity hoặc model confidence không đủ để verify identity.

## Outbox dùng để promote dữ liệu

Chỉ queue external candidate đã verified. Worker phải idempotent, chạy lại KG
duplicate detection, bảo toàn source/provider/freshness và ghi promoted entity
ID. Promotion chạy async; lỗi queue hoặc worker tạo metric/warning nhưng không
làm planning request thất bại.

## Test và điều kiện hoàn thành

Test KG short-circuit, provisional một nguồn, xác minh hai nguồn, conflict,
external timeout, call budget, duplicate promotion, idempotency và worker
failure. Hoàn thành khi không provisional place nào lọt vào planner eligibility.

## Hiện thực tại Checkpoint 5

- `retrieval_contract.py` định nghĩa query theo gap, evidence đã chuẩn hóa,
  candidate có trust state, provider attempt và promotion event.
- `retrieval.py` search các gap có thể giải quyết bằng candidate mới và luôn
  mở hai core pool có giới hạn cho `TravelPlace` và `Restaurant`. Gap identity,
  data quality và destination mismatch được giữ lại để xác minh/làm giàu,
  không tự thay bằng place khác.
- Thứ tự gọi là Knowledge Graph, internal source, sau đó tối đa hai external
  source. Đủ số candidate đã verify thì dừng và không gọi tầng sau.
- Candidate từ `SearchPlacesGapSource` luôn được scope bằng canonical ADM và gọi
  qua tool dùng chung `shared/tools/search_places` ở mode `requirement`.
- Candidate đã link KG được làm giàu qua `PlaceMetadataRepository` trước scoring
  để lấy duration, cost, opening và suitability nếu repository có dữ liệu.
  Repository lỗi hoặc thiếu field chỉ tạo warning/unknown, không bịa giá trị.
- Hai quota độc lập cùng tăng theo độ dài chuyến đi: `8 TravelPlace/ngày` và
  `8 Restaurant/ngày`, mỗi loại tối thiểu 12 và tối đa 60. Chuyến ba ngày có
  target `24 + 24 = 48`. Core query over-fetch tối đa 60 mỗi loại để bù
  candidate bị loại do metadata; scoring mới chốt quota. Đây là pool để Planner
  lựa chọn, không phải số stop bắt buộc phải xếp vào lịch.
- Generic `travel place` discovery xen kẽ `Special_Experience` và các
  `TravelPlace` khác trong đúng ADM. Non-special ưu tiên cạnh
  `Offer_Item -> ActivityItem`, sau đó metadata và rating/review. `Has_Style`
  chỉ fallback timing, không tạo category hoặc quota.
- Đồng thuận external yêu cầu hai provider khác nhau cùng khớp tên, ADM,
  category và tọa độ trong 0,5 km. Cùng tên/ADM nhưng khác category hoặc vị trí
  tạo `needs_review`.
- Một external source giữ trạng thái `provisional` và `planner_eligible=false`.
  Candidate KG legacy hoặc entity đã được admin duyệt là `verified_kg`. Entity
  Google Maps `pending` có property note `verification=not_verified` vẫn
  là provisional dù đã có KG ID; hai external source đồng thuận mới là
  `verified_external`.
- Google Maps Playwright là external fallback thực tế. Nó upsert candidate vào
  `knowledge_entities` dưới dạng `pending`, ghi provenance/fetch time trên từng
  property và chỉ tạo `Located_In` pending; không suy diễn `Special_Experience`,
  `Offer_Item` hoặc `Has_Style`.
- `PromotionWorker` kiểm tra duplicate lần cuối trước khi promote. Event ID được
  tạo ổn định theo candidate nên queue lặp lại không tạo event mới.

Checkpoint này vẫn chỉ có `InMemoryPromotionOutbox` cho development và unit
test. Direct Google draft persistence không thay thế promotion đã verify; chưa
có durable promotion worker. Lỗi queue/worker chỉ tạo warning hoặc trạng thái
failed, không đổi candidate đã verify thành lỗi planning.
