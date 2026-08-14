# Phase 05 — Durable checkpoint, summary và user-level memory

Cập nhật lần cuối: 2026-08-14

## Durable graph checkpoint

Thay `InMemorySaver` bằng Postgres-backed checkpointer sau khi structured memory ổn định. Checkpointer giữ workflow/resume state; không thay transcript hoặc facts.

Yêu cầu: migration/setup chính thức, cleanup/retention theo thread, nhiều worker và không lưu secret/raw third-party payload.

## Rolling summary

- Tạo summary sau N lượt hoặc khi token budget vượt ngưỡng.
- Summary có version, provider/model, thời gian và source message range.
- Summary lỗi thì giữ summary cũ và dùng recent messages.

## User-level preference memory

Chỉ lưu khi user nói rõ hoặc xác nhận. Fact phải có scope `user`, provenance, confidence và cơ chế xem/xóa. Không biến suy đoán tạm thời của một chuyến đi thành sở thích lâu dài.

## Nghiệm thu

- Restart/scale worker không mất context.
- Chat mới không lấy nhầm địa điểm chat cũ.
- User xóa được memory theo chat và preference theo user.
- Latency/token không tăng tuyến tính theo lịch sử.
