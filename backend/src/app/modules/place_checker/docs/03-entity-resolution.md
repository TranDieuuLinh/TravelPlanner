# Task 03: Phân giải entity

## Mục tiêu

Phân giải từng place mention thành canonical identity trong đúng ADM mà không
tự tạo place hoặc âm thầm chọn kết quả nhập nhằng.

## Phụ thuộc

Task 01-02 và capability dùng chung
`app.shared.tools.search_places.SearchPlacesTool`.

## Ranh giới sở hữu

Shared tool là nguồn luật duy nhất cho:

- chuẩn hóa tên và bỏ dấu;
- tìm theo canonical name và alias;
- lexical similarity;
- lọc ADM, loại địa điểm và stable identity;
- xếp hạng top-K, ngưỡng chấp nhận và margin;
- chống trùng các dòng do provider trả về;
- provider timeout/error và external fallback policy.

PlaceChecker không tự xây một công thức similarity thứ hai. PlaceChecker chỉ:

- chuyển `PlaceCandidateInput` và `TripEvaluationContext` thành request;
- khóa external fallback trong Checkpoint 2;
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
top_k = 5
allow_external_fallback = false
```

Không gọi tool nếu ADM chưa ở trạng thái `resolved`. Không đưa toàn bộ raw
prompt vào tool; `source_evidence` được giới hạn tối đa 500 ký tự.

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

- Named place yêu cầu score lớn hơn `0.82`.
- Margin với candidate thứ hai tối thiểu `0.08`.
- Score bằng đúng `0.82` không được tự động chấp nhận.
- Match sai ADM, thiếu tọa độ, thiếu stable identity hoặc mâu thuẫn type không
  đủ điều kiện resolve theo policy shared tool hiện tại.
- Tên mạnh nhưng address hint mâu thuẫn chuyển `needs_review`.
- Direct-user unresolved vẫn được giữ cùng candidate và protection metadata.
- Không gọi external provider trong Task 03, kể cả khi KG trả kết quả yếu.

## Mapping kết quả

`resolved` tạo selected canonical place. `needs_review` giữ top matches nhưng
không chọn place. `unresolved` giữ candidate gốc. `provider_error` được chiếu
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

External retrieval, corroboration và promotion thuộc Task 08. Khi đến Task 08,
caller mới được bật `allow_external_fallback` theo verification policy.

## Test và điều kiện hoàn thành

Test phải chạy qua `SearchPlacesTool` thật với provider in-memory, bao gồm exact,
alias, typo, khác dấu, margin thấp, sai ADM, address conflict, ADM chưa resolve,
provider timeout, direct-user unresolved và external không được gọi.

Hoàn thành khi PlaceChecker không còn normalization/scoring engine riêng, giữ
được provider attempts/reason và toàn bộ test shared tool vẫn đạt.
