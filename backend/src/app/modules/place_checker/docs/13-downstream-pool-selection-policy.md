# Chính sách bốc candidate cho flow sau PlaceChecker

## Ranh giới

PlaceChecker không gán ngày hoặc buổi. Module chỉ trả pool đã xác minh cùng:

- `experience:*` từ quan hệ `Special_Experience`;
- `item:*` từ quan hệ `Offer_Item`;
- opening hours và source time hint;
- preference matches, avoid conflicts và suitability;
- score, tọa độ, chi phí và data quality.

PlaceSelector/Final Planner áp tỷ lệ khi đã biết số slot sáng/tối. Không xóa
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

PlaceSelector cần trả thêm audit metadata: quota mong muốn/thực tế, fallback,
seed khám phá, cluster đã chọn và lý do loại candidate.
