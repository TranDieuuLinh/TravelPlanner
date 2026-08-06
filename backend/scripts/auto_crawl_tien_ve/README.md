# Auto crawl tiền vé

Package này chứa CLI nghiên cứu giá vé người lớn cho `TravelPlace` bằng Gemini
Google Search grounding. Chỉ kết quả có identity khớp và grounded source hợp lệ
mới được phép ghi vào `knowledge_properties.admission_price`.

Chạy từ thư mục `backend/`.

Dry-run và ghi resume cache:

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices.py \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 1
```

Xác minh và commit giá hợp lệ vào database:

```bash
.venv/bin/python scripts/auto_crawl_tien_ve/enrich_travel_place_prices.py \
  --apply \
  --limit 20 \
  --min-review-count 1000 \
  --concurrency 1
```

Cache mặc định nằm ở `backend/var/travel-place-price-research-v1.jsonl`.
