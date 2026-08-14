# Kế hoạch triển khai Conversation Memory

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Xây dựng lớp memory bền vững cho hội thoại lập kế hoạch du lịch. Memory giúp hệ thống hiểu các câu nối tiếp như “các điểm bên trên”, “chỗ đó” và “lịch trình vừa rồi”, đồng thời giữ đúng thông tin người dùng đã xác nhận.

## Hiện trạng

- `agent_trip_chat_messages` vẫn là transcript gốc; Conversation Memory tạo projection facts có provenance.
- Root graph hỗ trợ PostgreSQL checkpointer khi dependency/configuration đã bật, với fallback InMemory rõ ràng cho development.
- Explorer, Information Finder, Place Checker và Planner đã nhận projection memory compact.
- Place Checker xác minh địa điểm nhưng không nên sở hữu memory.
- Working memory theo `chat_id` và preference theo `user_id` đã có contract, repository và API đọc/xóa.

## Nguyên tắc

1. Tạo vertical module riêng `backend/src/app/modules/conversation_memory/`.
2. Module khác chỉ gọi public contract, không truy cập repository/state nội bộ.
3. Transcript là dữ liệu gốc; structured facts là projection có provenance.
4. Không âm thầm ghi đè thông tin user đã xác nhận.
5. Place Checker chỉ đọc context liên quan và trả domain result; Memory Service mới merge fact.
6. Không gửi toàn bộ lịch sử vào Gemini; dùng structured memory + summary + message gần nhất.
7. Schema phải có migration, test compatibility và cập nhật tài liệu.

## Thứ tự phase

| Phase | Kết quả chính |
|---|---|
| 00 | Baseline, contract và bộ test hành vi |
| 01 | Module memory và database schema |
| 02 | Extract/merge facts và context resolver |
| 03 | Tích hợp Trip Chat và Root Graph |
| 04 | Tích hợp Explorer, Place Checker, Planner |
| 05 | Durable checkpoint, summary và user preference |
| 06 | Integration, load, rollout và audit — đã triển khai test/flag/observability; production load chưa đánh giá |

Mỗi phase phải pass test của phase trước; không gộp toàn bộ vào một PR lớn.
