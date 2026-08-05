# ADR-005: Preference learning theo tầng và route ước tính có gắn nhãn

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-29

Phần persistence preference của ADR này được thay thế bởi ADR-019; quyết định
route vẫn còn hiệu lực.

## Bối cảnh

Explorer cần học từ prompt, URL, OCR và hành vi mà không buộc user trả lời thêm.
Nếu ghi trực tiếp mọi nội dung vào profile thì một Reel có thể bị hiểu sai thành
sở thích lâu dài và tạo rủi ro quyền riêng tư. Planner cũng cần thứ tự địa điểm
tốt hơn trước khi ADR-002 chọn route provider chính thức.

## Quyết định

1. Mỗi intake trả `PreferenceSnapshot` ngắn hạn dưới dạng JSON.
2. Chỉ signal chuẩn hóa đủ confidence được aggregate vào duy nhất cột JSON
   `users.travel_preferences`.
3. Profile dài hạn có version, explicit preferences, aggregate score,
   confidence, observation count, source type và timestamp; không lưu raw
   prompt/OCR/transcript.
4. Địa điểm tự động từ Explorer mặc định là `preferred`, không phải
   `must_visit`.
5. Planner nhận effective preference profile; explicit constraint của trip có
   quyền ưu tiên cao hơn.
6. Finder dùng tọa độ để chạy nearest-neighbour và 2-opt. Theo ADR-002 cập nhật,
   từng transport leg đi bộ/đường bộ sau đó được Valhalla xác minh; leg
   road provider lỗi phải fallback với `source=geodesic_estimate` và
   `verified=false`. Public transit chỉ tồn tại khi provider trả route transit
   xác minh, không dùng fallback đường chim bay.

## Hệ quả

- Có thể cá nhân hóa dần mà không ngắt flow bằng câu hỏi.
- Dữ liệu cũ dạng `string[]` được nâng cấp khi đọc/ghi mà không cần thêm cột
  user.
- Một Reel đơn lẻ chỉ tạo tín hiệu yếu; tín hiệu lặp lại mới tăng confidence.
- Thứ tự route hiện tại giảm đi vòng theo tọa độ nhưng chưa được tối ưu toàn cục
  bằng road-time matrix. Leg Valhalla phản ánh mạng đường và phương tiện nhưng chưa
  traffic-aware vì plan chưa có ngày đi.
