# ADR 002: Shared Gemini LLM client với key rotation

Cập nhật lần cuối: 2026-08-10.

## Trạng thái

Accepted cho capability LLM dùng chung; chưa chuyển các agent hiện có khỏi
deterministic behavior.

## Quyết định

Đặt port và adapter LLM tại `backend/src/app/shared/llm/` vì nhiều feature
module có thể dùng cùng capability này. Adapter gọi REST endpoint
`models.generateContent`, nhận system/user prompt và trả về text đầu tiên hợp lệ.

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
- Các agent hiện tại chưa tự động gọi LLM; thay đổi behavior của từng agent sẽ
  được thực hiện trong module sở hữu agent đó.
