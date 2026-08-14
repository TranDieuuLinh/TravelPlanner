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
Candidate không tính được giá dùng được từ `price_min`, `price_max`,
`typical_cost` hoặc tier `free` cũng là hard violation `missing_cost`; candidate
này không được chiếm quota reranking hoặc đi tiếp sang Planner.

Độ liên quan theo Knowledge Graph được ưu tiên cao trong điểm tìm kiếm.
Candidate có edge `Special_Near`, `Special_Experience`, `Offer_Item` hoặc
`Has_Style` với điểm neo/khu vực chứa điểm neo được xếp trước candidate chỉ
khớp từ khóa. Candidate keyword fallback vẫn được giữ để đủ pool nhưng phải có
nhãn `retrieval:keyword_fallback` và chịu penalty riêng. Quan hệ không thay thế
kiểm tra ADM, category và policy. `Near` legacy và `Must_Visit` không còn được
PlaceChecker đọc hoặc đưa vào scoring.

Điểm quan hệ không còn chỉ phụ thuộc tên edge: `Special_Near` giảm theo
`distance_km/threshold_km`; `Offer_Item` dùng confidence/status;
`Has_Style` dùng priority; `Special_Experience` pending có boost thấp hơn.
Keyword fallback chịu penalty `0.08`, relationship pending chịu penalty
`0.04`. Time window/duration mặc định được đọc từ node Style đích của
`Has_Style`; relationship properties có thể override theo từng attachment.
Các giá trị này chỉ lấp metadata còn thiếu, không ghi đè property trực tiếp
của place. Khi một place có nhiều Style, adapter giữ toàn bộ time window để
phủ các bữa/khung giờ tương ứng và dùng duration lớn nhất làm duration tổng
bảo thủ trong contract hiện tại.
Food retrieval giữ tối thiểu ba candidate cho mỗi ngày và interleave các
Style `breakfast`/`lunch`/`dinner`, để pool gửi sang Planner có coverage theo
từng bữa thay vì chỉ ưu tiên lexical match `restaurant`.

## Chọn quán cho món đặc trưng gần TravelPlace

Nhánh riêng đọc `ADM -> Special_Experience -> FoodItem`, sau đó tìm restaurant
có đồng thời `Special_Near` với TravelPlace và
`Restaurant -> Special_Experience -> FoodItem` trỏ tới đúng cùng FoodItem ID.
Không dùng tên để nối hai FoodItem. Việc ưu tiên được áp dụng theo từng
TravelPlace: nếu không có exact-ID special pair, nhánh mới dùng trực tiếp
FoodItem từ `Restaurant -> Offer_Item` và đánh dấu `offer_item_fallback`.
Mỗi TravelPlace nhận tối đa một selection. Candidate duy nhất của một FoodItem
không bị loại vì thiếu đối thủ; Bayesian weighted rating chỉ phân xử khi có
nhiều quán và pair score còn giữ priority/confidence của món, confidence offer,
độ tin cậy theo review count và khoảng cách. Service ưu tiên không tái sử dụng
cùng restaurant giữa các anchor khi còn lựa chọn khác.

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
- Candidate bị loại trước ranking khi identity chưa verify, sai ADM, thiếu giá
  hoặc duration cần cho Planner, đã đóng vĩnh viễn, xung đột avoid hoặc không phù hợp rõ ràng với
  children/infants.
- Penalty chẩn đoán hiện có: avoid conflict, lệch low budget, geographic outlier trên
  20 km, trùng trải nghiệm hiện có, trust thấp và metadata quá 90 ngày.
- Tổng penalty bị chặn ở 0,65; final score luôn nằm trong 0-1. Unknown metadata
  nhận điểm trung lập/thấp, không bị đổi thành free, open hoặc suitable.
- `reranking.py` chọn greedy theo cách xác định. Sau mỗi lựa chọn, candidate còn
  lại bị phạt nếu lặp category, experience type hoặc nằm trong bán kính 2 km
  của candidate đã chọn.
- Reranking giữ quota độc lập `12 TravelPlace/ngày` và
  `12 Restaurant/ngày`, tối đa 60 cho từng loại. Chuyến ba ngày vì vậy trả tối
  đa 36 candidate đủ điều kiện cho mỗi loại. Có thể truyền
  `reserve_limit_per_gap` để override trong test hoặc flow đặc biệt. Candidate
  trùng `candidate_key` giữa nhiều kết quả chỉ giữ bản có điểm tốt nhất.

Scoring ở checkpoint này chỉ áp dụng cho optional/system candidate do retrieval
tạo ra. Mandatory direct-user place vẫn thuộc evaluation của Task 06 và không
bị scoring/reranking thay đổi `mandatory`, `removable` hoặc tự loại. Projection
sang output cuối và workflow thuộc Checkpoint 6.
