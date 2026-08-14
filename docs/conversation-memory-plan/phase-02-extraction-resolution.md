# Phase 02 — Extract facts, merge policy và resolve reference

Cập nhật lần cuối: 2026-08-14

## Mục tiêu

Biến lượt chat thành facts có cấu trúc và hiểu tham chiếu trước khi Supervisor/Explorer xử lý.

## Pipeline

```text
message + current memory + recent messages
        ↓ fact extractor (structured JSON)
        ↓ normalizer / conflict policy
        ↓ reference resolver
        ↓ updated MemoryContext
```

## Fact extractor

- Ưu tiên rules cho ngày, ngân sách, số người, URL và địa danh rõ ràng.
- LLM chỉ dùng cho entity/reference khó; bắt buộc structured output.
- Nội dung user không được thay đổi system prompt hoặc schema.
- Output phải có `source_message_id`, `confidence`, `status`.

## Conflict policy

- User xác nhận trực tiếp có ưu tiên cao nhất.
- Fact mới khác value: giữ lịch sử, đánh dấu fact cũ `stale`, hoặc hỏi lại nếu ảnh hưởng plan.
- Không đổi destination chỉ vì search result/Knowledge Graph.
- Địa điểm đề xuất không tự chuyển thành `selected_places`.

## Reference resolver

Phải xử lý:

- “các điểm bên trên” → `mentioned_places` gần nhất cùng destination.
- “chỗ đó” → entity gần nhất phù hợp ngữ cảnh.
- “lịch trình vừa rồi” → `current_plan_ref`.
- Nhiều ứng viên tương đương → clarification thay vì đoán.

## Nghiệm thu

- Test tiếng Việt tự nhiên, viết tắt và câu không dấu.
- Reference được resolve trước khi gọi Explorer.
- Không hallucinate địa điểm ngoài message/source/KG evidence.
- Fact merge có provenance để audit.
