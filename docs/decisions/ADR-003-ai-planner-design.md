# ADR-003: AI Planner nhiều giai đoạn, ưu tiên lược đồ

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-27
- Cập nhật: bước confirm bắt buộc của Explorer intake được ADR-004 thay thế bằng
  tự động lưu kèm resolution status; các phần còn lại vẫn giữ nguyên.

## Bối cảnh

Một phản hồi model tự do duy nhất rất khó kiểm tra, chỉnh sửa, so sánh, bổ sung
route hoặc bảo toàn qua nhiều lần chỉnh sửa. Code hiện tại đã tách trách nhiệm
Explorer, Planner, PlaceSelector, Check và Backup. Tầm nhìn MVP còn yêu cầu biến URL
video thành `SelectedPlaces`; nếu trộn nội dung nguồn không đáng tin trực tiếp
vào Planner thì khó kiểm tra provenance, độ tin cậy và xác nhận của user.

## Quyết định

Giữ Planner dưới dạng workflow nhiều giai đoạn với đầu ra trung gian bị ràng buộc
bởi schema. Thêm pipeline trước Planner nhưng giữ ranh giới xác nhận rõ ràng:

1. Import lấy nội dung được phép và lưu source/artifact.
2. Extract tạo claim và place candidate có evidence/confidence.
3. Resolve đối chiếu candidate với place chuẩn hóa.
4. User Confirm tạo `SelectedPlace`; candidate chưa xác nhận không phải intent.
5. Explorer chuẩn hóa sở thích và xác định nhu cầu hỏi thêm.
6. TripThemePlanner chạy một lượt research, backend kiểm chứng bằng Place
   database, rồi lượt thứ hai chỉ tạo `TripThemeDraft` ở cấp toàn chuyến.
7. PlaceSelector điền item chi tiết bằng địa điểm đã chuẩn hóa.
8. Check áp dụng validation theo quy tắc và dữ liệu provider.
9. Backup tạo một phương án riêng được liên kết khi user yêu cầu hoặc khi có rủi
   ro.

Code ứng dụng sở hữu ID, authorization, persistence, chuyển trạng thái, provider
call và kiểm tra bất biến. LLM có thể được thay thế qua `LLMClient`. Revision
phải có phạm vi rõ ràng và giữ nguyên item đã khóa.

## Hệ quả

- Có thể test và quan sát từng giai đoạn trung gian.
- Có thể retry import/extract/resolve độc lập và giữ kết quả từng phần.
- Planner không phụ thuộc payload của từng mạng xã hội.
- Cần thêm UI review vì xác nhận của user là một bước nghiệp vụ bắt buộc.
- UI có thể stream hoặc hiển thị tiến độ lập kế hoạch.
- Nhiều call và bước điều phối hơn có thể tăng độ trễ và chi phí.
- Capability tool chỉ xác minh coverage trong Place database. Khoảng cách vùng
  lân cận hiện là địa lý theo centroid, không thay thế route provider.
- Prompt, schema, tình huống đánh giá và hành vi thử lại có version trở thành yêu
  cầu vận hành.
- Plan chính và plan dự phòng vẫn có thể được kiểm tra độc lập.
