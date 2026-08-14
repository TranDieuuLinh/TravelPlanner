# Phase 03 — Tích hợp Trip Chat và Root Graph

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Mỗi lượt chat đọc memory bền vững trước khi route và ghi memory sau khi xử lý thành công. Phase 03 đã hoàn thành tích hợp giữa `TripChatService`, `ConversationMemoryService` và `RootGraph`.

## Trạng thái triển khai

- **TripChatService integration**: Trong `TripChatService.send()`, hệ thống load `WorkingMemoryState` từ `ConversationMemoryService`, tự động tạo projection/facts tạm thời trong bộ nhớ từ `current_itinerary` (legacy chat chưa có memory row) mà không ghi database trước graph execution. Facts từ user message mới được merge sau bootstrap facts để ưu tiên input hiện tại. Toàn bộ projection và facts mới chỉ được lưu atomically sau khi Root Graph thực thi thành công. Nếu graph thất bại, memory version/facts/projection giữ nguyên tuyệt đối.
- **Root State & Public Mapping**: `RootState` và `RootGraphInput` nhận context tùy chọn:
  - `conversation_memory` (`WorkingMemoryState`)
  - `recent_messages` (tối đa 10 message gần nhất)
  - `conversation_summary`
  - `resolved_references`
- **Supervisor Routing**: `SupervisorInput` nhận thông tin điểm đến, thời lượng, danh sách địa điểm đã đề cập, và cờ `clarification_required`. Nếu reference resolver phát hiện từ thay thế mơ hồ (ví dụ "chỗ đó" khi có nhiều địa điểm candidate), Supervisor trả câu hỏi làm rõ đích danh reference thay vì hỏi lại toàn bộ trip intent.
- **Concurrency & Failure Fallback**: Đã xử lý `MemoryVersionConflict` bằng cơ chế retry tự động. Nếu memory service/database lỗi, hệ thống ghi warning ngắn gọn và fallback về transcript-only execution mà không làm gián đoạn request hay phá vỡ dữ liệu lịch sử.
- **Backward Compatibility**: Giữ nguyên backward compatibility tuyệt đối cho `/v1/agent/invoke` và REST API schemas camelCase.

## Giới hạn và các bước Phase 04/05

Conversation Memory hiện đã sẵn sàng tích hợp hội thoại đa lượt trong Trip Chat. Việc làm giàu context chuyên sâu cho Explorer, Place Checker và Planner subgraph sẽ tiếp tục hoàn thiện trong Phase 04. Durable Checkpointer LangGraph và User Long-Term Preference sẽ được triển khai trong Phase 05.
