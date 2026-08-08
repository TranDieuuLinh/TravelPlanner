# Admission price crawler

`crawl_admission_prices.py` discovers ticket/admission pages, downloads public
HTML with the same secured `httpx` + Trafilatura reader used by Explorer, and
asks Gemini for a schema-validated standard adult daytime admission price.

The command is a database dry-run by default:

```bash
backend/.venv/bin/python crawl_data/crawl_admission_prices.py \
  --limit 10 \
  --min-review-count 1000
```

Write only verified results with an HTTP(S) source:

```bash
backend/.venv/bin/python crawl_data/crawl_admission_prices.py \
  --apply \
  --limit 10 \
  --min-review-count 1000 \
  --crawl-delay-seconds 10
```

Use Tavily for URL discovery when Google/Selenium is blocked:

```bash
backend/.venv/bin/python crawl_data/crawl_admission_prices.py \
  --search-provider tavily \
  --apply \
  --limit 10
```

`TAVILY_API_KEY` is required for Tavily. Gemini keys come from
`GEMINI_PRICE_API_KEYS` or `GEMINI_API_KEY` in `backend/.env`.

The crawler runs one place at a time. It also waits at least five seconds
between target-page download starts by default. Use
`--crawl-delay-seconds 10` (or a larger value) for a more conservative batch.
The Gemini request timer remains independently controlled by
`--min-interval-seconds`.

The crawler does not bypass CAPTCHA, login, paywall, robots controls, or
anti-bot protection. A failed static fetch falls back to the search provider's
snippet/rendered text unless `--strict-static` is set. Missing, ambiguous,
conflicting, or ungrounded prices are cached for review but never written as a
canonical price.

Verified data is stored in `knowledge_properties` with key
`admission_price`. The JSON snapshot contains the price, currency, unit,
freshness, confidence, model, and `sources`; the property's `source` column
also stores the primary final page URL. Existing prices are preserved unless
`--overwrite` is explicitly supplied.
