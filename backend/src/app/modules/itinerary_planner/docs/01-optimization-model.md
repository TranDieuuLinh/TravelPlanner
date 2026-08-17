Has_Style: Bia Hơi Đất Mỏ → Ăn nhậu (TravelPlace/Restaurant/DrinkDessert -> style)
Located_In: ADM1 Locted in ADM0, Places loacted in ADM...
Offer_Item: Places offer activity (normal activity)
Offer_Item: Places special expereince ( activity/places)
Special_Near: places->places

Phạm vi triển khai của module này bắt đầu từ public JSON đã được upstream
chuẩn bị. FinalItineraryPlanner không query Knowledge Graph, không search DB và
không sửa behavior của PlaceChecker.

Tài liệu triển khai chi tiết:

1. `02-input-boundary-and-preprocessing.md`
2. `03-valhalla-matrix-and-sparse-arcs.md`
3. `04-cp-sat-model-and-solving.md`
4. `05-runtime-testing-and-rollout.md`

TẦNG 1 — PRIORITY

1. Tối đa số user_input được xếp
2. Khóa kết quả
3. Tối đa số URL được xếp
4. Khóa kết quả

TẦNG 2 — HARD CONSTRAINTS

- duration đầy đủ
- nằm trong opening hours
- không overlap
- đủ travel time giữa hai stop
- tổng giá/người ≤ budget/người
- ba bữa/ngày
- mỗi candidate tối đa một lần
- route bắt đầu/kết thúc hợp lệ
- ngày thường kết thúc tối đa 23:00; nightlife/drinking có thể đến 03:00
- tối thiểu 7 giờ nghỉ trước stop đầu của ngày tiếp theo; không khóa thời lượng
  nghỉ cố định

TẦNG 3 — OBJECTIVE
Cộng:

- specialExperienceValue
- preferenceValue
- placeQualityValue
- timeFitValue
- relationshipValue cùng ngày

Trừ:

- activityDiversityCost
- foodDiversityCost
- travelTimeCost
- idleWaitingCost
- mealDeviationCost
- fatigueCost
- dayImbalanceCost
- unknownOpeningCost rất nhỏ
- sourceMixDeviationCost cho mục tiêu sáng 70/30 và tối 60/40 giữa
  Special Experience/Offer Item

Kết quả:
selected[i] = có chọn candidate i không
assigned[i,d] = có xếp i vào ngày d không
start[i,d] = phút bắt đầu
end[i,d] = phút kết thúc
arc[i,j,d] = ngày d có đi trực tiếp từ i sang j không
meal[f,d,m] = có chọn food f cho meal m của ngày d không
sourcePeriod[i,d,p] = stop i thuộc morning/evening theo giờ xếp thực tế
sourceSpecial/sourceOffer = vai trò source của stop trong buổi, `both` chọn một

Ví dụ:
selected[van_mieu] = 1
assigned[van_mieu, 1] = 1
start[van_mieu, 1] = 540 → 09:00
end[van_mieu, 1] = 630 → 10:30
