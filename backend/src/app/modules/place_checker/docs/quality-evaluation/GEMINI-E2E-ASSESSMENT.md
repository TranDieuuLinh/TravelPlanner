# Đánh giá 4 pool Explorer → PlaceChecker

File dữ liệu đầy đủ: `explorer_place_checker_gemini_e2e.json`.

## Tổng hợp

| Kịch bản | Pool | Hợp lệ | Có quan hệ KG | Tỷ lệ quan hệ | Nhóm địa điểm | Trạng thái |
|---|---:|---:|---:|---:|---|---|
| Văn hóa đầy đủ | 59 | 58 | 54 | 91.5% | 42 điểm tham quan, 9 đồ uống, 8 quán ăn | conditional |
| Ngân sách thấp | 46 | 45 | 40 | 87.0% | 36 điểm tham quan, 5 quán ăn, 4 đồ uống | conditional |
| Gia đình | 48 | 45 | 39 | 81.3% | 36 điểm tham quan, 5 quán ăn, 4 đồ uống | blocked |
| Mâu thuẫn nightlife | 34 | 30 | 28 | 82.4% | 22 điểm tham quan, 5 quán ăn, 3 đồ uống | blocked |

## Nhận xét

- Pool đủ lớn để Planner lựa chọn, đặc biệt kịch bản văn hóa có 59 điểm.
- Quan hệ Knowledge Graph đang có tác dụng: 81–92% candidate có ít nhất một tag quan hệ.
- Tuy nhiên category còn nghèo: phần lớn bị gom vào `travel_place`; chưa tách rõ workshop, performance, nature, outdoor, family và local_activity.
- Kịch bản gia đình có 3 candidate thiếu tên/category; kịch bản mâu thuẫn có 4; kịch bản ngân sách có 1.
- Output compact đã loại các candidate không có tên, nhưng full pool vẫn chứa chúng và cần làm sạch trước khi bàn giao Planner.
- Các gap chính là thiếu tọa độ/identity, chưa biết trạng thái mở cửa, phân tán địa lý và rủi ro ngân sách.

## Kết luận

Chất lượng hiện tại **đủ để thử nghiệm luồng chọn pool**, nhưng chưa đạt mức bàn giao production. Cần xử lý candidate thiếu identity/category và bổ sung phân loại trải nghiệm trước khi dùng pool làm đầu vào duy nhất cho Planner.
