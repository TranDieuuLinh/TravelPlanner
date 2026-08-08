# ADR-029: Conversation Supervisor chỉ phân loại

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-07

## Bối cảnh

Conversation Supervisor từng trả đồng thời `intent`, `agent`, `responseText`,
`operations`, `intakePatch` và clarification fields. Backend vẫn tự suy ra agent
từ intent rồi kiểm tra model có chọn đúng mapping hay không. Với
`travel_advice`, `InformationFinderAgent` chỉ phát lại `responseText`, khiến
Supervisor vừa phân loại vừa thực hiện một phần công việc của agent. Keyword
heuristic trước model còn có thể bỏ qua Gemini và ép câu hỏi kiến thức vào
Explorer khi draft chưa có destination.

## Quyết định

- Mọi turn được Gemini Supervisor phân loại bằng structured output trước khi
  dispatch; không dùng keyword heuristic để tự chọn intent.
- Supervisor output chỉ gồm `intent`, `confidence` và `arguments`.
- `arguments` là discriminated union với các kind `information`, `planning`,
  `mutation`, `clarification` và `command`; kind phải khớp intent.
- Model không trả `agent` hoặc user-facing `responseText`. Backend giữ mapping
  intent-agent duy nhất và dispatch đúng một handler.
- `InformationFinderAgent` sở hữu lượt LLM tạo câu trả lời. General advice dùng
  structured generation; câu hỏi cần độ mới dùng Gemini Google Search
  grounding; place search tiếp tục dùng Knowledge Graph/provider; explain-plan
  chỉ nhận snapshot plan hiện tại.
- Backend tiếp tục sở hữu schema validation, item-ID validation, confidence
  threshold, lock/confirmation policy, authorization và persistence.

## Hệ quả

- Supervisor có một trách nhiệm duy nhất và không còn dữ liệu agent trùng lặp.
- Câu trả lời kiến thức được tạo trong agent đọc-only, tách khỏi phân loại intent.
- Câu hỏi cần độ mới có source block khi grounding trả nguồn; không có grounding
  thì agent trả warning thay vì giả vờ đã xác minh.
- Mỗi câu hỏi thông tin thông thường dùng hai lượt model: một lượt phân loại và
  một lượt trả lời, làm tăng latency/chi phí nhưng ranh giới dễ kiểm thử hơn.
- Local runtime không có Gemini key vẫn phân loại được bằng Stub, nhưng không
  tạo nội dung tư vấn giả; InformationFinder trả trạng thái provider unavailable.
