# ADR-031: Preference Observer bền vững, tách khỏi Conversation Supervisor

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-07

## Bối cảnh

Conversation Supervisor chỉ phân loại intent để dispatch agent. Việc đọc
preference bằng keyword trong `PreferenceLearningService` trộn trách nhiệm hiểu
ngôn ngữ với aggregate domain, chỉ bao phủ từng câu hard-code và dùng task trong
process nên có thể mất khi runtime restart.

Một user message có thể đồng thời có conversation intent, preference dài hạn và
ràng buộc chỉ áp dụng cho chuyến hiện tại. Không thể biểu diễn ba lớp này bằng
một intent duy nhất hoặc tự động đưa mọi signal vào Traveler Profile.

## Quyết định

1. Giữ Conversation Supervisor là classifier-only; không thêm quyền ghi profile.
2. Mỗi user turn tạo một `PreferenceObservationJob` trong cùng transaction.
   Job unique theo message ID và không sao chép content.
3. Worker chỉ claim turn `completed`, đọc message hiện hữu rồi gọi
   `PreferenceExtractor` interface. Production dùng structured LLM output;
   local/test dùng deterministic adapter cùng contract.
   Turn `create_plan`/`regenerate_plan` được đánh dấu `skipped` vì Explorer đã
   tạo và persist PreferenceSnapshot giàu context hơn; observer không được cộng
   cùng message lần thứ hai.
4. `PreferencePolicy` chặn trait nhạy cảm, confidence thấp và signal không có
   global scope. Trip-scoped instruction tiếp tục thuộc TripIntent, không được
   thăng cấp thành long-term profile.
5. `PreferenceLearningService` chỉ merge signal đã chuẩn hóa. Repository giữ
   source type `trip_chat` và message ID gần nhất, không giữ raw message trong
   profile.
6. Merge profile và hoàn tất job dùng cùng transaction; retry cùng message không
   được tăng observation hai lần. Runtime recovery đưa job `running` về `queued`.

## Hệ quả

- Câu trả lời chat không chờ thêm một LLM call hoặc database profile write.
- Provider/extraction strategy có thể thay mà không sửa conversation orchestration.
- Có thêm worker, bảng job và một LLM call nền cho mỗi turn hoàn tất ở production.
- Signal chỉ áp dụng cho chuyến hiện tại chưa được observer tự ghi vào TripIntent;
  chúng phải đi qua workflow edit TripIntent có optimistic revision.
