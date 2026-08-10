# ADR 002: Shared Gemini LLM client với key rotation

Cập nhật lần cuối: 2026-08-10.

## Trạng thái

Accepted cho capability LLM dùng chung. Information Finder là module đầu tiên
có thể opt-in qua cấu hình; các module khác chưa tự động chuyển behavior.

## Quyết định

Đặt port và adapter LLM tại `backend/src/app/shared/llm/` vì nhiều feature
module có thể dùng cùng capability này. Adapter gọi REST endpoint
`models.generateContent`, nhận system/user prompt và trả về text đầu tiên hợp lệ.
Port hỗ trợ JSON Schema tùy chọn; client gửi `responseMimeType=application/json`
và `responseJsonSchema`, sau đó module gọi phải validate lại tại boundary.

Ứng dụng dùng một biến cấu hình duy nhất:

```env
GEMINI_API_KEY=api1,api2,api3
```

Client giữ thứ tự key và chọn round-robin. Key trả về lỗi quota, authorization,
transport hoặc server sẽ được cooldown rồi thử key tiếp theo trong cùng request.
Key không được ghi vào log hoặc exception message.

## Hệ quả

- Feature module không phải phụ thuộc trực tiếp vào Gemini SDK.
- `get_llm_client` tạo client dùng chung qua bootstrap; module cần LLM nên nhận
  `LlmClient` qua dependency injection.
- Xoay key trong process không thay thế rate limiting, billing isolation,
  secret management hoặc durable usage tracking ở production.
- Information Finder sở hữu prompt chống prompt injection, source budget,
  structured claim schema, citation validation và fallback. Shared client không
  chứa business rule du lịch hay source content.
- `gemini-2.5-flash` chỉ là baseline cấu hình được, chưa được production-evaluated;
  cần pin snapshot sau eval, cùng secret management, observability và cost limit.
