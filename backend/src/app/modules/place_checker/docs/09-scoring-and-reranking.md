# Task 09: Scoring và reranking

## Mục tiêu

Xếp hạng optional/system candidate trong một lượt, bảo vệ explicit user/URL
place và giữ component đủ để audit.

## Điểm cơ sở

```text
0.15 intent_match
0.10 preference_match
0.13 gap_value
0.10 budget_fit
0.08 geo_fit
0.06 people_fit
0.07 time_fit
0.05 quality
0.05 uniqueness
0.05 data_confidence
0.10 rating_quality
0.06 review_quality
```

Preference match đọc direct public tags của candidate/metadata. Tag phải là key
hiện có trong `auto-attach/tags-auto.yml`; technical provenance và relationship
type không được đưa vào `tags` để tạo preference match giả.

## Hard filter và penalty

Optional candidate bị loại nếu identity chưa verify, sai ADM, conflict avoid,
thiếu duration, thiếu cost bắt buộc, đã đóng vĩnh viễn hoặc không phù hợp rõ
ràng với children/infants. Accommodation được miễn duration; TravelPlace có thể
dùng planner cost mặc định theo price policy.

Penalty mềm gồm lệch low budget, geographic outlier, duplicate experience, trust
thấp, relationship pending và metadata quá 90 ngày. Tổng penalty bị chặn ở
0,65; final score nằm trong 0–1.

Explicit candidate từ user/URL không đi qua optional candidate selection. Nó
vẫn được evaluate và phát warning/constraint khi conflict, nhưng mandatory place
không bị ranking tự remove.

## Relationship signal

`Special_Experience`, `Special_Near` và `Offer_Item` giữ relationship score và
evidence riêng. Chúng là signal trong cùng result set, không tạo waterfall
query. Direct tags, rating/review và metadata quality cùng tham gia rank.

`Has_Style` không tạo semantic tag, candidate, category hoặc điểm rank. Adapter
chỉ dùng Style priority cao nhất có `time_duration`/`time_windows` để điền field
tương ứng còn thiếu; field trực tiếp của entity/item luôn thắng.

## Food selection

Food query dùng các TravelPlace và Entertainment cuối làm anchor. Một query trả
cả nearby và city-wide candidates; `Special_Experience -> FoodItem` và
`Offer_Item -> FoodItem` là hai evidence path độc lập. Không join FoodItem bằng
tên và không gọi `Offer_Item` là fallback.

Selector ưu tiên short preference, hard-filter avoid, cân bằng FoodItem và
anchor, dedup restaurant, sau đó kiểm tra breakfast/lunch/dinner cho mỗi ngày.
Một restaurant có thể cover nhiều anchor nhưng chỉ đếm một candidate. Target
pool là 6 restaurant/ngày.

## Quota sau rank

- TravelPlace: 12/ngày.
- Restaurant: 6/ngày.
- Entertainment: 2/ngày, window giao buổi tối từ 18:00.
- DrinkDessert: 3/ngày, window giao ban ngày 07:00–18:00.
- Accommodation: tối đa 3 toàn chuyến.

Các quota độc lập, dùng chung candidate-key/place-ID dedup. Entertainment và
DrinkDessert được chọn riêng rồi mới gộp vào `entertainment[]` với `entityType`.

## Test và điều kiện hoàn thành

Test component arithmetic, hard avoid, preference signal, deterministic rank,
quota độc lập, dedup, time-window inheritance, food meal/anchor coverage và
mandatory protection.
