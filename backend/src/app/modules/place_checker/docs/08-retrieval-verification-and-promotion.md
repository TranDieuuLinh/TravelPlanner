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
trực tiếp. Knowledge Graph dùng edge `Near` và `Must_Visit` để ưu tiên candidate
quanh điểm neo. Nếu điểm neo không có cạnh đủ trực tiếp, truy vấn mở rộng qua
ADM chứa điểm neo để đọc `Must_Visit` và `Special_Experience` của khu vực.
Candidate được gắn nhãn như `relation:near`, `relation:must_visit`,
`relation:area_special_experience` hoặc `retrieval:keyword_fallback` để
downstream giải thích được lý do chọn.

Thứ tự ưu tiên quan hệ là:

```text
Must_Visit trực tiếp
-> Near trực tiếp
-> Special_Experience/Offer_Item/Has_Style trực tiếp
-> Must_Visit/Special_Experience từ ADM chứa điểm neo
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

## Xác minh

- Kết quả link được KG: `verified_kg`.
- Một external source: `provisional`, chưa planner-eligible.
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
- `retrieval.py` chỉ search các gap có thể giải quyết bằng candidate mới. Gap
  identity, data quality và destination mismatch được giữ lại để xác minh/làm
  giàu, không tự thay bằng place khác.
- Thứ tự gọi là Knowledge Graph, internal source, sau đó tối đa hai external
  source. Đủ số candidate đã verify thì dừng và không gọi tầng sau.
- Candidate từ `SearchPlacesGapSource` luôn được scope bằng canonical ADM và gọi
  qua tool dùng chung `shared/tools/search_places` ở mode `requirement`.
- Candidate đã link KG được làm giàu qua `PlaceMetadataRepository` trước scoring
  để lấy duration, cost, opening và suitability nếu repository có dữ liệu.
  Repository lỗi hoặc thiếu field chỉ tạo warning/unknown, không bịa giá trị.
- Số candidate dự phòng tăng theo độ dài chuyến đi: mục tiêu `15 địa điểm/ngày`,
  tối thiểu 20 và tối đa 120 cho toàn bộ pool. Mỗi gap
  được cấp một phần giới hạn phù hợp. Đây là pool để Planner lựa chọn, không
  phải số địa điểm bắt buộc phải xếp vào lịch.
- Đồng thuận external yêu cầu hai provider khác nhau cùng khớp tên, ADM,
  category và tọa độ trong 0,5 km. Cùng tên/ADM nhưng khác category hoặc vị trí
  tạo `needs_review`.
- Một external source giữ trạng thái `provisional` và `planner_eligible=false`.
  Candidate có KG entity ID là `verified_kg`; hai external source đồng thuận là
  `verified_external`.
- `PromotionWorker` kiểm tra duplicate lần cuối trước khi promote. Event ID được
  tạo ổn định theo candidate nên queue lặp lại không tạo event mới.

Checkpoint này chỉ có `InMemoryPromotionOutbox` cho development và unit test.
Chưa có migration hoặc durable worker runtime vì ownership của database đích
chưa được khóa. Lỗi queue/worker chỉ tạo warning hoặc trạng thái failed, không
đổi candidate đã verify thành lỗi planning.
