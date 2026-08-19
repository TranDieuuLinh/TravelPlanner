# Phase 05 — Durable checkpoint, summary và user-level memory

Cập nhật lần cuối: 2026-08-14

## Durable graph checkpoint

Root graph dùng lazy `AsyncPostgresSaver` khi `DATABASE_URL` và package `langgraph-checkpoint-postgres` có mặt; nếu dependency chưa được cài, hệ thống log rõ ràng và chỉ fallback về `InMemorySaver` cho development. Checkpointer giữ workflow/resume state; không thay transcript hoặc facts.

Yêu cầu: migration/setup chính thức, cleanup/retention theo thread, nhiều worker và không lưu secret/raw third-party payload.

## Rolling summary

- Tạo summary sau N lượt hoặc khi token budget vượt ngưỡng.
- `RollingSummaryBuilder` tạo summary bounded sau tối thiểu 8 message, có version, provider/model, thời gian và source message range. Khi summary lỗi, summary cũ được giữ lại.
- Summary lỗi thì giữ summary cũ và dùng recent messages.

## User-level preference memory

Conversation Memory có API đọc/xóa user preference và chỉ nhận fact đã `confirmed_by_user=true`, chuyển sang `scope="user"`. Fact suy đoán tạm thời của một chuyến đi không được tự động nâng thành sở thích lâu dài.

## Nghiệm thu

- Restart/scale worker không mất context.
- Chat mới không lấy nhầm địa điểm chat cũ.
- User xóa được memory theo chat và preference theo user.
- Latency/token không tăng tuyến tính theo lịch sử.
