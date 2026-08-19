# Information Finder Structured Output Design

Ngày: 2026-08-17

## Mục tiêu

Information Finder trả về một câu trả lời tương thích ngược qua `answer` và
một danh sách `contentBlocks` có kiểu rõ ràng để frontend render theo semantic
content. Một assistant message vẫn là một message duy nhất; `content` và
`content_blocks` được lưu ở hai trường riêng trong cùng một row.

## Phạm vi và ranh giới

- Information Finder sở hữu block contracts, prompt, validation, normalization
  và fallback generator.
- TripChat chỉ vận chuyển và lưu public output; không chứa business rule lọc
  nội dung của Information Finder.
- Frontend render blocks khi có dữ liệu và giữ `MarkdownMessage` làm fallback.
- Runtime persistence là `agent_trip_chat_messages` từ migration `003`.
- Tạo migration additive mới cho `content_blocks`; không sửa hoặc dùng schema
  legacy `trip_chat_messages` trong migration `007`.
- Giữ nguyên các thay đổi chưa commit về entity linking, Knowledge Graph và
  MarkdownMessage.

## Contract

Tất cả model public của Information Finder dùng alias camelCase. Các block là
discriminated union theo trường `type`:

- `paragraph`: `text`, `source_ids`.
- `factList`: `title`, `items`; mỗi item có `label`, `text`, `highlights`,
  `source_ids`.
- `verse`: `title`, `author`, `lines`, `source_ids`.
- `quote`: `text`, `attribution`, `source_ids`.
- `recommendations`: `title`, `items`; mỗi item có `name`, `reason`,
  `source_ids`.
- `steps`: `title`, `items`; mỗi item có `text`, `source_ids`.
- `comparison`: `title`, `options`; mỗi option có `name`, `pros`, `cons`,
  `source_ids`.
- `notice`: `text`, `severity`, `source_ids`.

`GeneratedAnswer` có `answer_type`, `blocks`, `entity_candidates` và không
cho phép LLM tự tạo URL citation hoặc entity ID. Backend validate toàn bộ
`source_ids` với retrieved sources trước khi ánh xạ sang `SourceReference`.
`InformationFinderOutput` giữ `answer`, thêm `content_blocks`, và giữ
`sources`/`warnings`.

### Entity trong structured blocks

Structured output public có `inline_spans` trên các trường text của block hoặc
item. Đây là discriminated union riêng:

- `text`: `{ type: "text", text }`.
- `entity`: `{ type: "entity", text, entity_id }`.

`entity` span chỉ được backend tạo sau khi resolver xác nhận entity và có node
Knowledge Graph. LLM không được phép tạo `entity_id`; trong LLM output, model
chỉ cung cấp `entity_candidates`/tên thực thể như hiện tại. Backend chạy entity
linking trên từng block/item sau normalization rồi materialize các span theo
đúng thứ tự text. Phần text không resolve được giữ `type: "text"`, không có
link và không tạo preview.

Renderer dùng `inline_spans` để tạo text nodes và `InteractiveEntityLink` cho
span có `entity_id`; nó không tự tìm entity theo tên và không cần chạy
MarkdownMessage để giữ hover/click. Với `verse`, mỗi line là một text item có
`inline_spans`, nên line break và entity interaction cùng được bảo toàn.

## Data flow

1. Prompt cung cấp source excerpts đã giới hạn độ dài và yêu cầu LLM trả đúng
   schema blocks.
2. Structured generator parse Pydantic model.
3. Answering service validate source IDs, normalize text và tạo markdown/text
   tương thích ngược từ blocks.
4. Entity linker xử lý từng text field trong blocks, chỉ tạo entity span cho
   entity đã resolve; entity candidate chưa có node giữ text span plain.
5. Information Finder trả cả `answer` và `content_blocks` cùng danh sách sources
   đã được backend ánh xạ.
6. Root graph/TripChat truyền hai trường này vào assistant message.
7. Repository lưu `content` và JSON `content_blocks` riêng. Khi đọc row cũ,
   giá trị thiếu/null được chuẩn hóa thành `[]`.

## Nội dung và fallback

Prompt yêu cầu chỉ giữ 3–5 ý hữu ích trực tiếp cho khách du lịch, mỗi fact ngắn
và mỗi highlight là 1–3 cụm từ. Boilerplate tổng quát được loại bằng
normalizer trước khi tạo fallback, gồm navigation, breadcrumb, footer, tuyển
dụng, thông tin doanh nghiệp, quảng cáo, `Previous`, `Next`, `Trang chủ` và
fragment không hoàn chỉnh. Bộ lọc dựa trên pattern và relevance/query terms,
không hard-code theo một website.

Extractive fallback chọn câu sạch tại boundary câu/từ, tối đa 3–5 facts, mỗi
fact có source ID tương ứng. Fallback không suy đoán verse từ text vỡ cấu trúc.
Nếu không còn dữ liệu sạch, trả một paragraph ngắn có citation nguồn đầu tiên.

## Frontend

Thêm `AnswerBlockRenderer` và các renderer nhỏ cho tám block types. Renderer
chỉ nhận highlights và `inlineSpans` backend cung cấp, escape bằng React text
nodes, bỏ qua highlight không khớp và không dùng `dangerouslySetInnerHTML`.
Citation source và entity mention tiếp tục là hai cơ chế độc lập; entity có node
giữ hover/click preview hiện có, entity không có node là plain text.

Nếu `contentBlocks` không rỗng, chat dùng structured renderer; nếu rỗng, dùng
`MarkdownMessage` cũ. CSS đặt `white-space: normal` cho markdown message và
điều chỉnh list item/paragraph để marker thẳng hàng, không ảnh hưởng user
message hoặc plain-text bubble. Comparison dùng layout responsive dạng cards,
không dùng bảng phức tạp trên mobile.

## Migration và compatibility

Migration mới dùng `ALTER TABLE ... ADD COLUMN IF NOT EXISTS content_blocks
jsonb NOT NULL DEFAULT '[]'::jsonb` trên `agent_trip_chat_messages`. Existing
rows không cần backfill; contract khi đọc luôn trả `contentBlocks: []`. User
messages cũng dùng giá trị mặc định rỗng. Legacy schema không bị thay đổi.

## Kiểm thử và xác minh

- Information Finder: schema từng block, prompt, source ID validation,
  normalization, fallback bounds, citation và entity linking.
- TripChat: persistence round-trip, migration shape, message cũ thiếu blocks.
- Frontend: render từng block, line breaks, highlights, citations, entities,
  markdown fallback, XSS safety và responsive overflow.
- Chạy test bằng source path của repo clean và xác nhận `app.__file__` trỏ về
  `K:\VSF\VSF_TravelPlanner-clean\backend\src`.
- Chạy compileall backend, typecheck/lint frontend phù hợp và kiểm tra UI
  localhost nếu môi trường frontend cho phép.
