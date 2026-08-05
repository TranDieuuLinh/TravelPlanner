# ADR-017: Trích xuất website công khai bằng Trafilatura

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-04

## Bối cảnh

Planner đã nhận mọi URL ở UI nhưng runtime chỉ có connector chuyên biệt cho
YouTube, TikTok, Instagram và Facebook. URL website thông thường bị đưa nhầm qua
`yt-dlp`, nên không đáp ứng phạm vi MVP về blog/trang du lịch công khai. Dùng web
search trả phí cho URL mà user đã cung cấp làm tăng chi phí và không bảo đảm đọc
đúng trang cụ thể.

## Quyết định

1. URL không thuộc platform video đã nhận diện đi qua
   `WebPageExtractionService`, tách khỏi media connector nhưng trả cùng contract
   `UrlReelExtractionResult` trong giai đoạn tương thích.
2. Backend dùng `httpx` fetch trực tiếp và Trafilatura 2.1 để lấy main text dạng
   Markdown. Trafilatura là adapter extraction; domain Planner không nhận HTML
   hoặc object riêng của thư viện.
3. Fetch chỉ nhận HTTP/HTTPS công khai, không có userinfo. DNS của mỗi hop phải
   resolve hoàn toàn thành địa chỉ global; redirect, timeout, content type và
   kích thước response đều bị giới hạn.
4. Nội dung trang được coi là untrusted data. Structured text extractor hiện có
   phải bỏ qua instruction trong nguồn và trả observation có evidence/schema
   trước Aggregator/Resolver.
5. Lưu artifact loại `webpage` theo canonical URL nhưng chỉ giữ evidence span
   đã cấu trúc, không lưu toàn bộ bài viết. Cache `ExtractedContext` bằng schema
   version. Functional query được giữ, tracking query phổ biến bị loại.
6. Không dùng Playwright mặc định và không vượt đăng nhập, paywall, CAPTCHA hoặc
   kiểm soát truy cập. Browser rendering chỉ được thêm qua ADR riêng nếu có dữ
   liệu về coverage, chi phí và rủi ro.

## Hệ quả

- Blog và trang itinerary HTML công khai đi qua cùng job/provenance/Resolver với
  nguồn video mà không phát sinh phí web-search theo request.
- Static page có latency và tài nguyên thấp hơn browser automation.
- Website JavaScript-only hoặc chống bot có thể thất bại và phải cho retry hoặc
  thêm địa điểm thủ công.
- Runtime có thêm dependency Trafilatura/lxml và phải tiếp tục pin, quét lỗ hổng
  cùng container backend.
