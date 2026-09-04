# Task 03: Phân giải entity

## Mục tiêu

Phân giải từng place mention thành canonical identity trong đúng ADM, chọn
một candidate tốt nhất cho direct-user/URL input và giữ warning/provenance khi
identity chỉ ở trạng thái provisional.

## Phụ thuộc

Task 01-02 và capability dùng chung
`app.shared.tools.search_places.SearchPlacesTool`.

## Ranh giới sở hữu

Shared tool là nguồn luật duy nhất cho:

- chuẩn hóa tên và bỏ dấu;
- tìm thống nhất theo canonical name, alias và address trong ADM;
- lexical similarity;
- lọc ADM, loại địa điểm và stable identity;
- xếp hạng candidate, ngưỡng chấp nhận và address disambiguation;
- chống trùng các dòng do provider trả về;
- provider timeout/error và external fallback policy.

PlaceChecker không tự xây một công thức similarity thứ hai. PlaceChecker chỉ:

- chuyển `PlaceCandidateInput` và `TripEvaluationContext` thành request;
- chỉ cho phép Google Maps khi catalog không trả row nào;
- chuyển kết quả tool thành domain contract;
- bổ sung address conflict và protection policy cho direct-user place;
- giữ provider attempts, resolution reason và provenance.

## Request gửi shared tool

Mỗi candidate tạo một request:

```text
query = candidate.name
input_adm = ADM đã resolve ở Task 02
search_mode = named_place
address_hint = candidate hoặc source address hint
top_k = 1
allow_external_fallback = true
```

Không gọi tool nếu ADM chưa ở trạng thái `resolved`. Không đưa toàn bộ raw
prompt vào tool; `source_evidence` được giới hạn tối đa 500 ký tự.

PostgreSQL named-place query luôn search chung `TravelPlace`, `Restaurant`,
`DrinkDessert`, `Entertainment` và `Accommodation`; input/URL không bị giả định
là TravelPlace trước khi identity được chọn.

## Similarity thực tế

Shared tool so sánh query với canonical name và aliases bằng normalized exact,
token overlap, sequence similarity và containment. Công thức named-place hiện
tại là:

```text
combined_score =
    0.62 * name_similarity
  + 0.18 * adm_compatibility
  + 0.08 * address_compatibility
  + 0.07 * type_compatibility
  + 0.05 * data_confidence
```

Nếu không có address/type hint, shared tool dùng giá trị trung lập theo policy
của nó. PlaceChecker dùng nguyên score từ tool, không tính lại score.

`similarity_method` được chiếu thành:

- `exact`: query chuẩn hóa bằng canonical name;
- `alias`: name similarity bằng 1 nhưng canonical name khác query;
- `lexical_only`: match theo chữ còn lại;
- `semantic`: chỉ khi shared provider sau này trả `semanticSimilarity`.

Checkpoint 2 hiện chưa có semantic/vector provider production. Không được mô tả
semantic như behavior đã chạy chỉ vì enum đã dự phòng field này.

## Quy tắc chấp nhận

- Place Checker lấy catalog top-1, không mở branch Top-K và không lọc trước theo
  entity type.
- Có `address_hint` thì shared tool dùng hint để disambiguate/ranking; không có
  hint thì chọn kết quả đầu tiên theo ranking.
- Candidate direct-user/URL giữ nguyên provenance `input`/`url`; catalog row đã
  verify được chọn trực tiếp. Google Maps draft vẫn là `provisional` và cần
  admin review.
- Match sai ADM, thiếu tọa độ, thiếu stable identity hoặc mâu thuẫn type không
  đủ điều kiện resolve theo policy shared tool hiện tại.
- Tên mạnh nhưng address hint mâu thuẫn chỉ được chọn nếu có candidate khác
  hợp lệ; nếu không thì vẫn chuyển `needs_review`.
- Direct-user/URL có candidate hợp lệ sẽ được tự chọn provisional thay vì mở
  branch chọn match ở frontend.
- Chỉ gọi Google Maps khi Knowledge Graph trả zero candidate. Provider error
  hoặc một catalog top-1 bị conflict không được diễn giải thành zero result.

## Mapping kết quả

`resolved` tạo selected canonical place. `needs_review`/`unresolved` có candidate
hợp lệ sẽ tự chọn một option tốt nhất thành `provisional`; nếu không có candidate
hợp lệ hoặc provider lỗi thì giữ candidate gốc. `provider_error` được chiếu
thành unresolved có warning, retryable context và provider attempts; không bị
diễn giải thành không tồn tại địa điểm.

Mỗi match option giữ canonical/provider ID, name, coordinates, category,
address, component scores, rank, rejection reasons và source provider. Match
không có stable ID không được biến thành ID giả.

## Internal và external provider

Shared tool hiện có Knowledge Graph provider và external provider port, chưa có
internal normalized fallback riêng. Không được truyền internal provider vào
external slot vì sẽ làm sai provenance. Nếu cần internal fallback, phải mở rộng
shared orchestration hoặc tạo composite Knowledge Graph provider có contract rõ
ràng.

External discovery để lấp optional pool không thuộc Task 03 và bị tắt trong
runtime Task 08. External ở đây chỉ là recovery cho named-place zero result.

## Test và điều kiện hoàn thành

Test phải chạy qua `SearchPlacesTool` thật với provider in-memory, bao gồm exact,
alias, typo, khác dấu, margin thấp, sai ADM, address conflict, ADM chưa resolve,
provider timeout, direct-user unresolved, catalog hit không gọi external và
catalog zero-result mới gọi external.

Hoàn thành khi PlaceChecker không còn normalization/scoring engine riêng, giữ
được provider attempts/reason và toàn bộ test shared tool vẫn đạt.
