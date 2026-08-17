# Chính sách bốc candidate cho flow sau PlaceChecker

## Ranh giới

PlaceChecker không gán ngày hoặc buổi. Module chỉ trả pool đã xác minh cùng:

- `experience:*` từ quan hệ `Special_Experience`;
- `item:*` từ quan hệ `Offer_Item`;
- opening hours và source time hint;
- preference matches, avoid conflicts và suitability;
- score, tọa độ, chi phí và data quality.

Pool có hai quota độc lập: reserve 14 `TravelPlace`/ngày và 10 `Restaurant`/ngày.
Food hard feasibility vẫn là unique matching cho ba meal slot/ngày; reserve 10
không thay thế meal-window gate.
Restaurant đi vào compact `food`, không bị trộn thành activity place. Đây là
candidate reserve; FinalItineraryPlanner vẫn chỉ xếp số stop khả thi theo thời
gian, bữa ăn và route.
Khi food selection bổ sung quán ghép với TravelPlace, compact builder ưu tiên
quán user-requested rồi quán đã ghép và vẫn chặn tổng Restaurant theo quota.

TravelPlace selector dùng coverage mềm trên phần candidate retrieval cần thêm:

- khoảng 6/14 có evidence `Special_Experience` thật;
- khoảng 4/14 có popularity signal từ Bayesian quality và `log(reviewCount)`;
- phần còn lại theo ranking diversity/preference/geography đã có.

Candidate được dedup giữa bucket; thiếu bucket thì ranking chung bù đủ target.
Đây là reserve toàn chuyến `14 × days`, không phải quota cứng cho từng itinerary
day. FinalItineraryPlanner áp tỷ lệ khi đã biết số slot sáng/tối. Không xóa
candidate khỏi PlaceChecker chỉ vì chưa được bốc vào một slot.

## Thứ tự điều kiện

```text
hard constraints
-> mandatory places
-> opening/time compatibility
-> geographic cluster
-> source mix
-> preference/exploration mix
-> budget soft tie-break
```

Tỷ lệ không được vượt qua hard avoid, closed status, sai ADM hoặc không phù hợp
rõ ràng với trẻ em/infants.

## Tỷ lệ nguồn activity

Phân loại candidate:

- `special_activity`: có `experience:*`, ưu tiên venue không phải restaurant/
  drink-dessert;
- `offer_item`: có `item:*`, hoặc là restaurant/drink-dessert;
- candidate có cả hai được xếp theo mục đích slot và không được đếm hai lần.

Mục tiêu theo từng nhóm slot:

| Buổi | Special activity | Offer item |
| --- | ---: | ---: |
| Sáng | 70% | 30% |
| Tối | 60% | 40% |

Dùng largest-remainder để làm tròn. Ví dụ 3 slot sáng thành 2 special + 1
offer; 5 slot tối thành 3 special + 2 offer.

Nếu một nhóm không đủ candidate, lấy phần thiếu từ nhóm còn lại và ghi
`quota_fallback`; không để slot trống và không đưa candidate chưa verify vào.

Trước source/popularity fill, reserve giữ một candidate cho mỗi tag KG có ý
nghĩa khi giới hạn pool cho phép. Tag kỹ thuật và generic `travel_place` không
tạo diversity group. `pool_category` chỉ ghi query intent đã tìm ra candidate,
không được coi là category/tag thật và không tham gia diversity. `Has_Style`
được tách thành `styles` ở compact boundary thay vì dùng làm tag diversity.
Relationship `Special_Experience` pending không tạo special slot. Query khám
phá chỉ nhận relationship candidate khi relation/style term khớp; Special
Experience chung không bypass điều kiện này.

## Tỷ lệ sở thích và khám phá

Chỉ áp dụng khi người dùng có `shortPreferences`:

- 80% candidate có preference match;
- 20% candidate khám phá từ phần còn lại.

Phần khám phá dùng pseudo-random có seed từ `request_id` để cùng input/data
snapshot cho cùng kết quả, nhưng request khác có thể đa dạng. Nếu không có sở
thích, bỏ tỷ lệ 80/20 và xếp theo quality, diversity, geography.

Nếu candidate phù hợp sở thích không đủ 80%, fallback sang candidate khám phá
đủ điều kiện và ghi lý do. Direct-user mandatory place không bị tỷ lệ này loại.

## Khoảng cách

Tạo 2-4 cluster từ coordinates. Chọn cluster chứa nhiều mandatory anchors nhất
trước; mỗi ngày ưu tiên một cluster. Candidate ngoài 20 km chỉ vào reserve khi
không còn candidate cùng loại trong cluster phù hợp. PlaceChecker chỉ cung cấp
coarse distance; route matrix cuối vẫn thuộc Planner.

## Budget

Budget không hard-filter pool trừ khi Explorer truyền explicit hard amount.
Trong cùng source/preference/cluster bucket, ưu tiên free/low cho budget thấp.
Unknown cost nằm sau known-compatible nhưng không bị đổi thành 0 ở domain
PlaceChecker.

## Dữ liệu output hiện dùng được

- `checkedPlaces[].tags`: phân biệt special/offer;
- `checkedPlaces[].opening` và `timePreferences`: xét sáng/tối;
- `checkedPlaces[].evaluation.preferenceMatches`: nhóm 80%;
- `checkedPlaces[].coordinates`: cluster;
- `checkedPlaces[].cost`: soft budget;
- `checkedPlaces[].verification` và `evaluation`: quality gate.

Compact planner contract hiện mang `sourceKind`, `offeredActivityIds` và
`timeSource`. `sourceKind=both` được solver gán đúng một nhóm trong từng buổi,
không đếm hai lần. Timing ưu tiên source hint trực tiếp, sau đó
`ActivityItem.time_windows`, rồi `Has_Style.time_windows`; opening hours của
place vẫn là hard feasibility boundary.

FinalItineraryPlanner đã áp quota source-mix theo thời điểm stop thực sự được
xếp: morning khi kết thúc không muộn hơn 12:00, evening khi bắt đầu từ 18:00.
Quota dùng largest-remainder và penalty mềm được clamp theo availability; thiếu
nhóm nào không bị phạt và được bù bằng nhóm còn lại trong cùng buổi. Output
`sourceMix` vẫn giữ policy target chưa clamp, actual,
`quotaFallback` và reason. Seed khám phá, geographic cluster audit và policy
80/20 vẫn là phần chưa triển khai; coverage special/popular của reserve đã được
triển khai trước bước Planner.
