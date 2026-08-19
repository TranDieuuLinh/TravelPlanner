# Phase 01 — Conversation Memory module và lưu trữ bền vững

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Tạo nguồn memory chính thức theo `chat_id`, tách khỏi `InMemorySaver` và không làm thay đổi API transcript.

## Module mới

Tạo `backend/src/app/modules/conversation_memory/`:

```text
public.py       # contract được module khác dùng
contract.py     # MemoryFact, ConversationMemory, MemoryContext
ports.py        # MemoryRepository, MemoryExtractor, SummaryProvider
service.py      # load, merge, resolve policy, save
adapters/postgres.py
tests/
```

## Contract tối thiểu

`MemoryFact` gồm: `key`, `value`, `value_type`, `scope`, `status`, `confidence`, `source`, `source_message_id`, `observed_at`, `expires_at`.

`ConversationMemory` gồm: `chat_id`, `destination`, `duration_days`, `travelers`, `budget`, `preferences`, `avoids`, `mentioned_places`, `selected_places`, `current_plan_ref`, `pending_goal`, `last_route`, `summary`, `version`.

## Database

Tạo migration do memory module sở hữu:

- `agent_conversation_memory` — một row hiện hành cho mỗi chat.
- `agent_conversation_memory_facts` — facts có version/provenance.
- Unique/index theo `chat_id` và normalized value.
- Không lưu raw prompt/secret ngoài transcript hiện có.

Ghi exchange và memory phải cùng transaction hoặc dùng optimistic version/`SELECT ... FOR UPDATE` để không lệch state.

## API nội bộ

- `load_context(chat_id, user_id)`
- `record_facts(chat_id, facts, expected_version)`
- `resolve_reference(chat_id, text)`
- `mark_stale(chat_id, keys)`

## Nghiệm thu

- Restart container vẫn load memory.
- Hai request đồng thời không mất update.
- Fact `confirmed` không bị fact suy luận confidence thấp ghi đè.
- Migration chạy được trên database mới và database đã có `agent_trip_chats`.
