# Beam Search parallel runtime

Cập nhật lần cuối: 2026-08-21.

Đây là runtime Beam-first. Ứng dụng ưu tiên Beam Search qua factory
`build_valhalla_beam_first_itinerary_planner_graph`; prefix preprocessing và
routing matrix chỉ chạy một lần. Nếu Beam trả lỗi, kết quả `PARTIAL` hoặc
timeline không hợp lệ, node Hybrid CP-SAT dùng lại cùng prepared/routing state
làm fallback và output nhận warning tương ứng. Factory
`build_beam_search_itinerary_planner_graph` vẫn cho phép kiểm thử Beam Search
độc lập.

Beam Search nhận `PreparedPlanningProblem` và `RoutingProblem` sau global
Valhalla matrix. Mỗi transition phải đạt các hard checks sau:

- matrix cell reachable và không nối hai restaurant liên tiếp;
- nếu distance từ Q3 trở lên, điểm đến phải có adjusted Bayesian rating tối thiểu
  3.0 và
  review count từ Q2/P50 trở lên;
- `safeTravel` được quy đổi từ giây sang phút, sau đó cộng với duration của
  điểm đến và phải nằm trọn trong một opening/time window;
- thời gian chờ giữa thời điểm đến và window kế tiếp không quá 45 phút;
- food/drink-desserter được xếp theo meal order, tối đa ba điểm leisure-food,
  và không vượt budget cứng.
- nếu số restaurant trong ngày còn dưới 3, Beam có thể thêm restaurant stop
  không gắn meal trong window 11:00–13:00 hoặc 18:00–20:00; rule
  restaurant-to-restaurant vẫn được áp dụng cho stop bổ sung này.
- Chỉ travel place bị loại khi ID đã xuất hiện trong nhánh/ngày trước; food và
  leisure có thể lặp nếu cần. Khi xếp hạng các nhánh, Beam ưu tiên ít lặp theo
  thứ tự entertainment, drink/dessert rồi restaurant.

`MatrixCell.food_to_food` là cờ dẫn xuất sau khi chuẩn hóa candidate từ
PlaceChecker. Provider Valhalla chỉ trả duration, distance và reachability;
provider không cần biết loại venue. Beam vẫn kiểm tra loại candidate để tránh
nhầm khi nhiều candidate dùng chung một tọa độ vật lý.

Thứ tự ưu tiên category của Beam là lexicographic: đủ 3 restaurant trước,
sau đó số travel place, đủ 2 restaurant, leisure đa dạng, drink/dessert,
entertainment rồi 1 restaurant. Một plan có cả drink/dessert và entertainment
được ưu tiên hơn plan chỉ có drink/dessert dù plan sau có nhiều drink/dessert
hơn. Quality, preference, style, time fit, travel, budget, diversity,
relationship và restaurant coverage là các điểm mềm dùng để tie-break.
Quality có weight 35; hệ số quality theo loại là travel place 1.50,
restaurant 1.10, drink/dessert 0.95 và entertainment 0.85. Mỗi travel place
khác nhau trong cùng ngày còn nhận thêm day-coverage bonus tăng dần, nên ngày
có nhiều travel place unique được ưu tiên hơn ngày ít travel place.
Ở bước tổng hợp cuối của mỗi nhánh, mỗi travel place còn cộng thêm
`travelplace_final_weight = 10` vào branch score.

Output Beam thêm `evaluation` với min/max/median của adjusted Bayesian rating,
review count và distance meters; counter JSON cho tags/styles/items; số lượng
restaurant, drink/dessert, entertainment, travel place; tổng giá và score.
Rating gốc vẫn được giữ trong stop metadata để bảo toàn provenance; output stop
thêm `bayesianRating` cho giá trị dùng khi xếp hạng. CP-SAT output vẫn hợp lệ
và để `evaluation` là `null` khi đi qua graph cũ.

Giới hạn mặc định là beam width 32 và tối đa 16 stop/ngày. Một global deadline
bao phủ mọi ngày và mọi nhánh backtracking, không reset theo `_search_day`:
10 giây cho một ngày, 20 giây cho 2–3 ngày và 30 giây cho chuyến dài hơn. Vòng
candidate kiểm tra deadline định kỳ; complete incumbent được giữ khi hết giờ,
còn incomplete plan chuyển Hybrid fallback. Đây là giới hạn bảo vệ runtime,
không phải bằng chứng optimality.
