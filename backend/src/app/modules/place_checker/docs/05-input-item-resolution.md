# Task 05: Phân giải input item

## Mục tiêu

Phân giải food, activity và experience requirement thành venue có canonical ID
mà không coi tên món ăn hoặc hoạt động là một Place.

## Phụ thuộc

Task 02-04, `SearchPlacesTool` và tùy chọn `PlaceMetadataRepository`.

## Luồng hiện tại

```text
item "pho"
-> PlaceSearchRequest(search_mode=requirement, ADM=Hanoi)
-> SearchPlacesTool
-> canonical venue candidates
-> lọc avoid/people incompatibility
-> ưu tiên khoảng cách, budget và preference
-> selected venue + tối đa 4 alternatives
```

Request luôn có `allow_external_fallback=false` trong Checkpoint 3. External
retrieval thuộc Task 08.

## Liên kết với địa điểm chơi và khoảng cách

Nếu item có `relatedPlaceName`, PlaceChecker tìm place tương ứng trong danh sách
đã resolve bằng tên canonical, tên gốc và alias:

- Nếu item là món ăn và place liên quan vốn đã là nhà hàng/quán cà phê, dùng
  trực tiếp place đó, không search thêm quán khác.
- Nếu item là món ăn nhưng place liên quan là điểm tham quan, tọa độ điểm tham
  quan trở thành mốc cho `SearchPlacesTool.previous_place`.
- Kết quả search được tính lại khoảng cách sau khi lấy metadata từ database.
  Tối đa 2 km là `nearby`, trên 2 đến 5 km là `acceptable`; quá 5 km bị loại khi
  người dùng đã liên kết rõ item với một place.
- Nếu không có `relatedPlaceName`, dùng tâm tọa độ thô của các điểm tham quan đã
  biết làm mốc. Candidate trên 15 km bị loại để tránh gợi ý lệch cụm chuyến đi.
- Không có tọa độ thì giữ trạng thái khoảng cách `unknown`; không bịa khoảng
  cách và không loại chỉ vì thiếu dữ liệu.

Khoảng cách ở đây là đường chim bay để chọn candidate. Thời gian đi đường thật,
thứ tự ghé và route matrix vẫn thuộc Final Planner.

## Mapping item type

- `food`, `meal` -> `restaurant`;
- `drink`, `coffee` -> `cafe`;
- `accommodation` -> `hotel`;
- `activity`, `experience`, `attraction` -> `travel_place`;
- type chưa biết không tạo type giả; shared tool tìm theo requirement/tag.

## Contract đầu ra

Mỗi `ResolvedInputItem` giữ item gốc, normalized requirement, status, selected
venue, tối đa bốn alternative, confidence kết hợp, selection reason, evidence,
provider attempts, warning và special experience nếu có.

Status:

- `resolved`: có venue hợp lệ đạt requirement threshold của shared tool;
- `partially_resolved`: có venue hợp lệ nhưng score chưa đủ để tự chọn;
- `unresolved`: không có venue hợp lệ, provider lỗi hoặc ADM chưa rõ.

Không có status nào được phép tạo synthetic place ID hoặc tọa độ.

## Context filter và ranking

Shared tool sở hữu base score. PlaceChecker không tính lại base score mà chỉ
xếp lại các option hợp lệ theo context:

1. loại option có provider rejection;
2. loại option xung đột với `short_avoids` theo canonical taxonomy dùng chung
   (so trên name, category và tags; ví dụ `alcohol` khớp `cocktail`);
3. nếu metadata đã biết, loại option không phù hợp children/infants;
4. loại candidate vượt ngưỡng khoảng cách khi có mốc;
5. với budget `low`, ưu tiên low/medium trước high/premium;
6. ưu tiên candidate gần mốc hơn;
7. ưu tiên tag/category khớp preference;
8. giữ thứ tự score của shared tool khi các yếu tố trên bằng nhau.

Metadata không có vẫn là unknown và không làm option bị loại. Metadata provider
lỗi trả partial item output cùng warning.

## Special experience

Item loại `activity` hoặc `experience` chỉ tạo `SpecialExperience` sau khi đã
chọn được canonical anchor place. Output giữ action, requirement, evidence và
`anchor_place_id`; không tự suy ra time slot từ evidence.

## Test và điều kiện hoàn thành

Test gồm phở resolve thành quán thật, dùng trực tiếp related food place, ưu tiên
quán gần related attraction, alternatives, partial match, không có
venue, type chưa biết, special experience, avoid filter, low-budget rerank,
children suitability, provider timeout và external không được gọi.

Hoàn thành khi item resolution tách khỏi named-place resolution, không tạo place
giả và mọi quyết định đều giữ provider provenance.
