# Phase 00 — Baseline và contract freeze

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Đo được lỗi hiện tại và khóa contract trước khi viết memory logic. Không triển khai service, database repository, hay migration thật của Phase 01 trong phase này.

## Việc cần làm

1. Ghi flow `PlannerPage` → `/v1/trip-chats/{id}/messages` → `TripChatService` → root graph.
2. Tạo bộ test baseline hành vi deterministic (dùng fake/stub classifier và dev explorer, không gọi Gemini API thật hay cloud database):
   - “Hà Nội có gì chơi?” → trích xuất destination ban đầu.
   - “Lên plan các điểm bên trên trong 3 ngày.” → tái hiện gap chưa nhớ context lượt trước, trả câu hỏi làm rõ.
   - “Thêm chỗ đó vào ngày 2.” → tái hiện gap đại từ thay thế "chỗ đó" chưa được resolve.
   - Restart backend (tạo graph instance mới với cùng `thread_id`) → tái hiện mất state do `InMemorySaver`.
   - User đổi destination → contract biểu diễn cả lịch sử facts và provenance (policy merge/stale/confirmation sẽ triển khai ở Phase 02).
3. Chốt vocabulary contract: `fact`, `reference`, `summary`, `working_memory`, `user_preference`.
4. Chốt JSON bên ngoài dùng camelCase; Python dùng snake_case, kiểm tra strict validation (`extra="forbid"`), giới hạn excerpt `source_text` (tối đa 200 ký tự, không chứa payload nhạy cảm).

- `backend/src/app/modules/conversation_memory/contract.py` [Hoàn thành]
- `backend/src/app/modules/conversation_memory/public.py` [Hoàn thành]
- Unit tests: `backend/src/app/modules/conversation_memory/tests/test_contract.py` [Hoàn thành]
- Integration baseline: `backend/tests/test_conversation_memory_baseline.py` [Hoàn thành]
- Mapping state hiện tại → memory state (`RootStateMemoryMapping`) [Hoàn thành]

> [!NOTE]
> Phase 00 chỉ khóa contract và ghi nhận baseline gaps. Module `conversation_memory` chưa triển khai database migration, MemoryService hay extraction thật; các tính năng này sẽ được triển khai trong Phase 01 và Phase 02.

## Nghiệm thu

- [x] Có test tái hiện lỗi “các điểm bên trên” trước khi sửa (`test_case_02_multiturn_deictic_reference_baseline_gap`).
- [x] Có test tái hiện đại từ “chỗ đó” đứng trong ngữ cảnh multi-turn (`test_case_03_pronoun_reference_baseline_gap`).
- [x] Có test tái hiện mất memory khi restart backend dùng cùng `thread_id` (`test_case_04_restart_checkpoint_memory_loss_baseline`).
- [x] Contract hỗ trợ serialization camelCase, forbid unknown fields và unresolved reference.
- [x] Transcript hiện có không bị xóa hoặc đổi nghĩa.
- [x] Tách biệt `WorkingMemoryState` với `Itinerary`.

