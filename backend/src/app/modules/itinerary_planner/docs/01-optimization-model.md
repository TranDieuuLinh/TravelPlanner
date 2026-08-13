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




Explorer
   ↓
PlaceChecker đọc Knowledge Graph
   ↓
PlaceChecker tạo candidate pool hoàn chỉnh
   ↓
Xuất đúng một JSON trip + places + food
   ↓
FinalItineraryPlanner validate JSON
   ↓
Gọi Valhalla lấy global matrix
   ↓
Tạo biến + hard constraints CP-SAT
   ↓
Tối ưu user_input
   ↓ khóa
Tối ưu URL
   ↓ khóa
Tối ưu planUtility
   ↓
Lấy route chi tiết cho arc được chọn
   ↓
Trả itinerary + unscheduled