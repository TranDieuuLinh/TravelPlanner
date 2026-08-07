# Auto crawl tiền vé

Package này chứa CLI nghiên cứu giá vé người lớn cho `TravelPlace`. Luồng mặc
định lấy canonical name, tìm Google bằng câu `giá vé của <tên địa điểm>`, dùng
Selenium mở kết quả organic đầu tiên, lấy text đã render rồi đưa content và URL
đó vào Gemini để trích xuất JSON giá có schema. Chỉ kết quả khớp identity và có
source HTTP(S) hợp lệ mới được ghi vào `knowledge_properties.admission_price`.

Chạy từ thư mục gốc repository.

Dry-run và ghi resume cache:

```bash
backend/.venv/bin/python tool-crawl/crawl-price/enrich_travel_place_prices.py \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 4
```

Xác minh và commit giá hợp lệ vào database:

```bash
backend/.venv/bin/python tool-crawl/crawl-price/enrich_travel_place_prices.py \
  --apply \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 4
```

Cache mặc định nằm ở `backend/var/travel-place-price-research-v1.jsonl`.
Pool key đọc từ `GEMINI_PRICE_API_KEYS`, phân tách bằng dấu phẩy, rồi fallback
về `GEMINI_API_KEY` trong `backend/.env`; không ghi API key trực tiếp vào source.
Các request price mặc định bắt đầu cách nhau ít nhất bốn
giây; có thể chỉnh bằng `--min-interval-seconds`. Khi toàn bộ pool trả quota
limited, batch ngừng cấp địa điểm mới và giữ phần còn lại cho lần chạy sau.
Nhiều key cùng Google project không làm tăng quota project. Summary cuối lệnh
luôn trả `admission_price_in_database` là tổng số price property hiện có trong
PostgreSQL.

Price research mặc định dùng `gemini-3.5-flash-lite` cho structured output,
không bật Gemini Google Search grounding khi provider là Selenium.

Provider mặc định `--search-provider google_selenium` cần Chrome/Chromium.
Selenium Manager tự tìm driver phù hợp. Provider chạy tuần tự, không bypass
consent, CAPTCHA, paywall hoặc trang chặn automation; khi Google chặn, outcome
trả `google_selenium_blocked` và không ghi DB. Content trang bị giới hạn trước
khi gửi vào LLM và luôn được coi là dữ liệu không tin cậy. Sau khi mở kết quả,
provider chờ mặc định 3 giây cho trang render; sau mỗi search chờ thêm 1 giây
trước địa điểm kế tiếp. Có thể chỉnh bằng
`GOOGLE_SELENIUM_PAGE_LOAD_WAIT_SECONDS` và
`GOOGLE_SELENIUM_POST_SEARCH_DELAY_SECONDS`.

Fallback vận hành không dùng Gemini grounding là Tavily basic search. Tạo free
API key, thêm vào `backend/.env` rồi chạy:

```env
TAVILY_API_KEY=tvly-...
```

```bash
backend/.venv/bin/python tool-crawl/crawl-price/enrich_travel_place_prices.py \
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
backend/.venv/bin/python tool-crawl/crawl-price/enrich_travel_place_prices_from_sources.py \
  --sources-file var/admission-price-sources.jsonl \
  --apply \
  --limit 20 \
  --concurrency 4
```

Script này vẫn chỉ ghi DB khi Gemini trả được giá người lớn tiêu chuẩn hoặc
miễn phí với HTTP(S) source hợp lệ. Nếu source không có giá, mâu thuẫn, hoặc đã
có `admission_price` mà không bật `--overwrite`, record sẽ bị bỏ qua.
