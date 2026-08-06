# Auto crawl tiền vé

Package này chứa CLI nghiên cứu giá vé người lớn cho `TravelPlace` bằng Gemini
Google Search grounding. Chỉ kết quả có identity khớp và grounded source hợp lệ
mới được phép ghi vào `knowledge_properties.admission_price`. CLI xử lý tối đa
bốn request đồng thời và cache/commit từng kết quả ngay khi request đó hoàn tất,
không chờ toàn bộ batch.

Chạy từ thư mục `backend/`.

Dry-run và ghi resume cache:

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices.py \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 4
```

Xác minh và commit giá hợp lệ vào database:

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices.py \
  --apply \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 4
```

Cache mặc định nằm ở `backend/var/travel-place-price-research-v1.jsonl`.
Pool key đọc từ `GEMINI_PRICE_API_KEYS`, phân tách bằng dấu phẩy, rồi fallback
về `GEMINI_API_KEY`. Các request price mặc định bắt đầu cách nhau ít nhất bốn
giây; có thể chỉnh bằng `--min-interval-seconds`. Khi toàn bộ pool trả quota
limited, batch ngừng cấp địa điểm mới và giữ phần còn lại cho lần chạy sau.
Nhiều key cùng Google project không làm tăng quota project. Summary cuối lệnh
luôn trả `admission_price_in_database` là tổng số price property hiện có trong
PostgreSQL.

Price research mặc định dùng `gemini-3.5-flash-lite`. Model inference và
structured output có thể khả dụng trên free tier, nhưng Google Search grounding
yêu cầu quota/billing riêng. Project không có grounded-search quota phải bật
billing hoặc cấu hình một search provider khác; xoay model Gemini không thay thế
được quota của tool.

Adapter thử nghiệm `--search-provider google_playwright` tách Google SERP search
khỏi Gemini grounding và ép concurrency xuống 1. Adapter không bypass consent,
CAPTCHA hoặc trang chặn automation; khi Google chặn, outcome trả
`google_playwright_blocked` và không ghi DB. Vì cả Chromium headless lẫn headed
đều bị chặn trên môi trường local đã kiểm tra, adapter này không phải mặc định.

Fallback vận hành không dùng Gemini grounding là Tavily basic search. Tạo free
API key, thêm vào `backend/.env` rồi chạy:

```env
TAVILY_API_KEY=tvly-...
```

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices.py \
  --apply \
  --limit 10 \
  --concurrency 1 \
  --search-provider tavily
```

CLI fail-fast nếu thiếu key. Tavily chỉ cung cấp kết quả tìm kiếm chuẩn hóa;
Gemini 3.5 Flash-Lite tạo structured price JSON mà không bật Google Search tool.
Free tier hiện có 1.000 basic-search credits mỗi tháng, nên không đủ crawl toàn
bộ catalog 14.000+ entity trong một lần.

Nếu đã có nguồn từ Codex/web search/manual crawler, dùng Gemini chỉ để trích
xuất và xác minh giá từ snippet/content đã đưa vào, không bật Google Search
grounding:

```jsonl
{"entityId":"travel_place_1","sources":[{"title":"Official tickets","uri":"https://official.example/tickets","snippet":"Giá vé người lớn hiện tại là 70.000 VND."}]}
```

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices_from_sources.py \
  --sources-file var/admission-price-sources.jsonl \
  --apply \
  --limit 20 \
  --concurrency 4
```

Script này vẫn chỉ ghi DB khi Gemini trả được giá người lớn tiêu chuẩn hoặc
miễn phí với HTTP(S) source hợp lệ. Nếu source không có giá, mâu thuẫn, hoặc đã
có `admission_price` mà không bật `--overwrite`, record sẽ bị bỏ qua.
