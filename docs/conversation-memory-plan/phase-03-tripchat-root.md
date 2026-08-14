# Phase 03 — Tích hợp Trip Chat và Root Graph

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Mỗi lượt chat đọc memory bền vững trước khi route và ghi memory sau khi xử lý thành công.

## Trip Chat

Trong `TripChatService.send()`:

1. Load chat, revision, current itinerary và `MemoryContext`.
2. Load rolling summary + tối đa 6–10 message gần nhất.
3. Extract/resolve message mới.
4. Truyền context đã chuẩn hóa vào root graph.
5. Sau kết quả, thu thập facts từ route output và ghi memory cùng transaction với exchange.

Không truyền raw toàn bộ `TripChat` vào module khác.

## Root state/public mapping

Bổ sung public context tối thiểu:

```text
conversation_memory
recent_messages
conversation_summary
resolved_references
```

Root orchestration chỉ map contract và điều phối; business rule merge/conflict vẫn ở memory module.

## Supervisor

Supervisor nhận current message, structured memory, resolved references, current itinerary status và summary. Prompt phải quy định follow-up có đủ context thì route đúng agent, không hỏi lại destination vô lý.

## Backward compatibility

- Chat cũ chưa có memory row: bootstrap từ transcript gần nhất và current itinerary.
- Memory service lỗi: fallback với current message và warning rõ ràng.
- Không phá endpoint `/v1/agent/invoke`; context mới là tùy chọn.

## Nghiệm thu

- Cùng `chat_id` qua restart vẫn giữ destination.
- VERSION_CONFLICT không mất memory update.
- Route, answer, itinerary và memory version cùng phản ánh một lượt.
