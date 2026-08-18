# Chính sách bốc candidate cho flow sau PlaceChecker

Cập nhật lần cuối: 2026-08-18.

## Ranh giới

PlaceChecker không gán ngày hoặc buổi. Module chỉ trả pool đã xác minh cùng:

- `experience:*` từ quan hệ `Special_Experience`;
- `item:*` từ quan hệ `Offer_Item`;
- opening hours và source time hint;
- preference matches, avoid conflicts và suitability;
- score, tọa độ, chi phí và data quality.

Pool có ba quota độc lập: reserve 22 `TravelPlace`/ngày, 16 `Restaurant`/ngày
và 6 `DrinkDessert`/`Entertainment` mỗi ngày. TravelPlace tăng để bảo vệ
preflight; trong compact pool, Entertainment chỉ mở buổi sáng có cap tối đa
một candidate/ngày. Candidate có thể xếp chiều/tối vẫn được giữ làm reserve.
Target 22 TravelPlace/ngày điều khiển retrieval và ranking. Hard handoff gate
riêng chỉ yêu cầu 8 TravelPlace/ngày; vì vậy pool đủ lớn để Planner tối ưu sẽ
không bị chặn chỉ vì nguồn live không lấp đầy toàn bộ reserve mong muốn.
Ba Style bữa chính active mặc định cho meal feasibility. Style food/drink khác
chỉ active khi resolve từ preference hoặc input Item. Food reserve chọn Item
trước, target mềm `2 × days` cho mỗi Style active, rồi truy ngược `Offer_Item`
sang `Restaurant`/`DrinkDessert`.
Trong từng anchor region, Item và quán chưa dùng được ưu tiên; Item chỉ được lặp
khi lựa chọn khác đã cạn. Food hard feasibility vẫn là unique matching cho ba
meal slot/ngày; Style coverage không thay thế meal-window gate.
Restaurant đi vào compact `food`; DrinkDessert/Entertainment đi vào compact
`entertainment`, không bị trộn thành activity place. Đây là
candidate reserve; FinalItineraryPlanner vẫn chỉ xếp số stop khả thi theo thời
gian, bữa ăn và route.
Khi food selection bổ sung quán ghép với TravelPlace, compact builder ưu tiên
quán user-requested rồi quán đã ghép và vẫn chặn tổng Restaurant theo quota.

TravelPlace selector dùng coverage mềm trên phần candidate retrieval cần thêm:

Core retrieval luôn có query `famous landmark must see top attraction`, query
`iconic historic landmark museum temple old quarter` và query `authentic local
cultural special experience` riêng, không phụ thuộc query chung `travel place`
hay theme query. Entertainment reserve dùng query ưu tiên `water puppet`, nhà
hát, biểu diễn văn hóa, live music và evening show thay cho từ khóa
`entertainment` chung dễ trả về doanh nghiệp dịch vụ.
Khi số TravelPlace đủ điều kiện còn thấp hơn hard handoff tối thiểu, query
`authentic local cultural special experience` vẫn được thêm ngay cả khi phần
thiếu chỉ còn một vài candidate; adaptive query budget không được chỉ chọn query
generic đầu tiên rồi block mà chưa thử recovery theo trải nghiệm đặc trưng.

- khoảng 8/14 có evidence hoặc provenance tag `Special_Experience` đã duyệt;
- khoảng 4/14 có popularity signal từ Bayesian quality và `log(reviewCount)`;
- phần còn lại theo ranking diversity/preference/geography đã có.

Popular candidate phải có ít nhất 500 review và popularity score từ 0,70;
mọi candidate chỉ có review signal nhưng chưa đạt hai ngưỡng này không được tính
đã lấp popular target. Trước scoring/quota/compact projection, semantic category
guard chuyển các tên/tag rõ ràng là music box, karaoke, golf, billiard/bi-a,
bowling, studio, game center, massage/trị liệu, spa hoặc retail store/souvenir
từ `TravelPlace` sai sang `Entertainment`.
Provenance `pool_category=shopping` là tín hiệu tổng quát cho cùng mapping, tránh
phải hard-code từng thương hiệu retail từ nguồn live.
Ở compact boundary, provider note được dùng làm semantic context để chuyển art
supply store, photo booth, garden center, plant service và venue thương mại
tương tự khỏi TravelPlace trước khi áp cap Entertainment.
Food-name guard sửa nguồn gắn nhầm quán phở/bún/cơm/lẩu/mì thành leisure về
`Restaurant` trước khi chia quota.

Candidate được dedup giữa bucket; thiếu bucket thì ranking chung bù đủ target.
Đây là reserve TravelPlace toàn chuyến `22 × days`, không phải quota cứng cho từng itinerary
day. FinalItineraryPlanner áp tỷ lệ khi đã biết số slot sáng/tối. Không xóa
candidate khỏi PlaceChecker chỉ vì chưa được bốc vào một slot.

Entertainment tùy chọn do hệ thống tìm phải có Bayesian-adjusted rating tối
thiểu 4,2/5. Candidate direct-user/URL không qua quality gate này. Candidate
cửa hàng hoặc dịch vụ thương mại (clothing/souvenir/ceramic shop, event
planner) bị tourist-suitability gate loại khỏi optional Entertainment dù rating
cao. DrinkDessert phải có tín hiệu đồ uống/tráng miệng rõ ràng; candidate có
note món ăn đặc trưng bị loại khỏi leisure pool. Với candidate
có toàn bộ time window kết thúc không muộn hơn 12:00, compact selector chỉ giữ
tối đa một candidate/ngày. Candidate có thể xếp chiều hoặc tối vẫn cạnh tranh
trong quota chung để Planner dùng làm phương án buổi tối.
Đây là giảm reserve trước Planner, không phải gán lịch tại PlaceChecker.

Selector Style tổng quát hoạt động trước thematic retrieval. Preference được
resolve sang Style ID; input Item được resolve bằng canonical name/alias sang
Item ID. Style có Item đi theo `Style <- Has_Style - Item <- Offer_Item - holder`;
Style không có Item dùng direct holder `Has_Style`. Holder hợp lệ gồm
`TravelPlace`, `Restaurant` và `DrinkDessert` trong đúng cây ADM. Mỗi Style
active có target `2 × days`; một `place_id` chỉ được chọn một lần trong pool.
Thứ tự fill là Style deficit, requested Item deficit, tag ít dùng,
relationship, quality và khoảng cách anchor. Bộ đếm chỉ tồn tại trong request.
Thiếu dữ liệu trả coverage và reason theo Style, không tạo candidate giả.

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
Phần fill cuối ưu tiên tag ít xuất hiện và soft-cap một tag rộng ở tối đa 3
candidate khi còn tag khác để thay thế. PostgreSQL adapter ánh xạ
`entity_type` thành `category` canonical; các bước downstream tiếp tục
chuẩn hóa `category` trước khi chia pool. Alias
`cafe`/`coffee`/`DrinkDessert` được xem là `drink_dessert`, còn `place_id`
không bị đổi theo category để giữ khả năng truy vết.
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
