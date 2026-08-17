# Phase 02 — Extract facts, merge policy và resolve reference

Cập nhật lần cuối: 2026-08-17

## Trạng thái Phase 02: HOÀN THÀNH (Internal Module)

Đã triển khai hoàn chỉnh pipeline trích xuất facts, xử lý xung đột memory (merge policy) và phân giải tham chiếu ngôn ngữ (reference resolution) trong module `conversation_memory`.

> [!NOTE]
> Phase 02 triển khai hoàn chỉnh contract, ports, rule-based extractor, reference resolver và service APIs. Tích hợp trực tiếp vào Root Orchestration/LangGraph runtime được giữ lại để triển khai trong Phase 03.

## Pipeline Đã Triển Khai

```text
message + current memory + recent messages
        ↓ RuleBasedFactExtractor (structured facts + provenance)
        ↓ MergePolicyEvaluator (confirmed facts protection + history superseding)
        ↓ HybridLlmReferenceResolver (semantic) → RuleBasedReferenceResolver fallback
        ↓ ConversationMemoryService.process_message / append_facts
```

## Các Thành Phần Chính

### 1. Ports & Interfaces (`ports.py`, `public.py`)
- `FactExtractor`: Port interface định nghĩa `extract_facts`.
- `ReferenceResolver`: Port interface định nghĩa `resolve_references`.
- `RuleBasedFactExtractor`: trích xuất fact deterministic, hỗ trợ tiếng Việt có dấu, không dấu và các viết tắt phổ biến.
- `HybridLlmReferenceResolver`: mặc định dùng Gemini để hiểu tham chiếu từ transcript gần đây, summary và active facts; kiểm tra mọi target fact ID. Tên địa điểm động chưa có fact chỉ được nhận khi xuất hiện nguyên văn trong transcript/memory. Provider lỗi, confidence thấp hoặc output không hợp lệ sẽ fallback sang `RuleBasedReferenceResolver`.

### 2. Fact Extraction (`extractor.py`)
- Trích xuất tự động: `destination`, `duration`, `travelers`, `budget_tier`, `place_candidate`, `start_date`, `note`.
- Phân biệt câu lệnh xác nhận/thay đổi trực tiếp ("Đổi sang Đà Nẵng") với câu hỏi giả định ("Có thể đi Đà Nẵng không?").
- Mọi fact đều ghi nhận provenance đầy đủ: `source_turn`, `source_message_id`, `source_excerpt` (tối đa 200 ký tự), `extracted_by`, `confidence` (0.0 - 1.0) và `status`.

### 3. Conflict Policy & Merge Evaluation (`merge_policy.py`)
- Fact được user xác nhận trực tiếp (`confirmed_by_user=True`) có ưu tiên cao nhất, không bị ghi đè bởi fact suy luận unconfirmed.
- Fact mới có giá trị khác sẽ chuyển fact cũ thành `superseded` để bảo toàn lịch sử audit.
- `place_candidate` không tự động chuyển thành `selected_places`.

### 4. Reference Resolver (`resolver.py`)
- "các điểm bên trên", "những địa điểm trên" → `deictic` reference phân giải thành danh sách địa điểm đã đề xuất.
- "chỗ đó", "nó", "địa điểm này" → `anaphora` reference. Nếu có duy nhất 1 ứng viên thì resolve chính xác; nếu có nhiều ứng viên tương đương thì trả `clarification_required = True` để hỏi lại user, tuyệt đối không đoán hay hallucinate.
- "lịch trình vừa rồi", "plan cũ" → `plan_ref` reference tới `current_plan_ref`.

## Service Public APIs (`service.py`)
- `extract_facts(message, current_memory, turn, message_id)`
- `resolve_references(message, current_memory)`
- `merge_extracted_facts(current_memory, extracted_facts)`
- `process_message(chat_id, user_id, message, turn, message_id)`

## Bộ Test Vừa Triển Khai
- `backend/src/app/modules/conversation_memory/tests/test_extraction_resolution.py`: Kiểm thử toàn bộ 16 kịch bản trích xuất, phân giải và quy tắc bảo vệ fact.
