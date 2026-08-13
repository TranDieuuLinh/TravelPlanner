# Task 09: Scoring và diversity reranking

## Mục tiêu

Xếp hạng optional/system candidate cho open gap trong khi vẫn bảo vệ mandatory
user intent.

## Phụ thuộc

Task 08.

## Điểm cơ sở

```text
0.18 intent_match
0.12 preference_match
0.16 gap_value
0.12 budget_fit
0.10 geo_fit
0.08 people_fit
0.08 time_fit
0.05 quality
0.06 uniqueness
0.05 data_confidence
```

Chuẩn hóa mỗi component về 0-1 và giữ lại component value để audit.

## Điểm phạt

Áp dụng penalty có giới hạn cho high-cost mismatch, geographic outlier,
duplicate experience, low verification và stale operational data. Optional
candidate có avoid conflict được đánh dấu hard violation và loại trước ranking;
avoid penalty chỉ còn là thông tin chẩn đoán, không thể giúp candidate quay lại.

Độ liên quan theo Knowledge Graph được ưu tiên cao trong điểm tìm kiếm.
Candidate có edge `Must_Visit`, `Special_Near`/`Near`, `Special_Experience`, `Offer_Item` hoặc
`Has_Style` với điểm neo/khu vực chứa điểm neo được xếp trước candidate chỉ
khớp từ khóa. Candidate keyword fallback vẫn được giữ để đủ pool nhưng phải có
nhãn `retrieval:keyword_fallback` và chịu penalty riêng. Quan hệ không thay thế
kiểm tra ADM, category và policy.

Điểm quan hệ không còn chỉ phụ thuộc tên edge: `Special_Near` giảm theo
`distance_km/threshold_km`; `Offer_Item` dùng confidence/status;
`Has_Style` dùng priority; `Special_Experience` pending có boost thấp hơn.
Keyword fallback chịu penalty `0.08`, relationship pending chịu penalty
`0.04`. Time window/duration của `Has_Style` chỉ lấp metadata còn thiếu, không
ghi đè property trực tiếp của place.

## Xếp hạng lại

Dùng deterministic greedy reranking. Sau khi chọn mỗi optional candidate, phạt
các candidate phía sau nếu lặp category, experience type hoặc geographic
cluster. Giữ reserve có giới hạn cho từng gap.

Mandatory place có thể có diagnostic score, nhưng score không được thay đổi
mandatory/removable state hoặc remove place.

## Test và điều kiện hoàn thành

Test component arithmetic, penalty bound, low-budget preference, nightlife
avoid, deterministic tie, category diversity, cluster diversity và mandatory
protection. Hoàn thành khi ranking giải thích được và ổn định với cùng input và
data snapshot.

## Hiện thực tại Checkpoint 5

- `scoring.py` chấm mọi retrieved candidate và giữ đủ 10 component trong output
  để audit. Tổng trọng số đúng bằng 1.
- Candidate bị loại trước ranking khi identity chưa verify, sai ADM, đã đóng
  vĩnh viễn, xung đột avoid hoặc không phù hợp rõ ràng với children/infants.
- Penalty chẩn đoán hiện có: avoid conflict, lệch low budget, geographic outlier trên
  20 km, trùng trải nghiệm hiện có, trust thấp và metadata quá 90 ngày.
- Tổng penalty bị chặn ở 0,65; final score luôn nằm trong 0-1. Unknown metadata
  nhận điểm trung lập/thấp, không bị đổi thành free, open hoặc suitable.
- `reranking.py` chọn greedy theo cách xác định. Sau mỗi lựa chọn, candidate còn
  lại bị phạt nếu lặp category, experience type hoặc nằm trong bán kính 2 km
  của candidate đã chọn.
- Mỗi gap giữ số candidate dự phòng theo số ngày: mục tiêu `15 địa điểm/ngày`,
  tối thiểu 20 và tối đa 120 cho toàn bộ pool. Có thể
  truyền `reserve_limit_per_gap` để override trong
  test hoặc một flow đặc biệt. Candidate trùng `candidate_key` giữa nhiều kết
  quả chỉ được giữ bản có điểm tốt nhất.

Scoring ở checkpoint này chỉ áp dụng cho optional/system candidate do retrieval
tạo ra. Mandatory direct-user place vẫn thuộc evaluation của Task 06 và không
bị scoring/reranking thay đổi `mandatory`, `removable` hoặc tự loại. Projection
sang output cuối và workflow thuộc Checkpoint 6.
