# ADR-003: AI Planner nhiều giai đoạn, ưu tiên lược đồ

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-27

## Bối cảnh

Một phản hồi model tự do duy nhất rất khó kiểm tra, chỉnh sửa, so sánh, bổ sung
route hoặc bảo toàn qua nhiều lần chỉnh sửa. Code hiện tại đã tách trách nhiệm
Explorer, Planner, Finder, Check và Backup.

## Quyết định

Giữ Planner dưới dạng workflow nhiều giai đoạn với đầu ra trung gian bị ràng buộc
bởi schema.

1. Explorer chuẩn hóa sở thích và xác định nhu cầu hỏi thêm.
2. Planner tạo macro plan.
3. Finder điền item chi tiết bằng địa điểm đã chuẩn hóa.
4. Check áp dụng validation theo quy tắc và dữ liệu provider.
5. Backup tạo một phương án riêng được liên kết khi user yêu cầu hoặc khi có rủi
   ro.

Code ứng dụng sở hữu ID, authorization, persistence, chuyển trạng thái, provider
call và kiểm tra bất biến. LLM có thể được thay thế qua `LLMClient`. Revision
phải có phạm vi rõ ràng và giữ nguyên item đã khóa.

## Hệ quả

- Có thể test và quan sát từng giai đoạn trung gian.
- UI có thể stream hoặc hiển thị tiến độ lập kế hoạch.
- Nhiều call và bước điều phối hơn có thể tăng độ trễ và chi phí.
- Prompt, schema, tình huống đánh giá và hành vi thử lại có version trở thành yêu
  cầu vận hành.
- Plan chính và plan dự phòng vẫn có thể được kiểm tra độc lập.
