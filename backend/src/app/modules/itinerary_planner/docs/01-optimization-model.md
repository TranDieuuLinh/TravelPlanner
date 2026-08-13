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
- overnight đến tối đa 03:00

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

Kết quả:
selected[i] = có chọn candidate i không
assigned[i,d] = có xếp i vào ngày d không
start[i,d] = phút bắt đầu
end[i,d] = phút kết thúc
arc[i,j,d] = ngày d có đi trực tiếp từ i sang j không
meal[f,d,m] = có chọn food f cho meal m của ngày d không

Ví dụ:
selected[van_mieu] = 1
assigned[van_mieu, 1] = 1
start[van_mieu, 1] = 540 → 09:00
end[van_mieu, 1] = 630 → 10:30
