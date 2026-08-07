"""Import organized festivals from Vietnam's public national festival portal."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://lehoi.com.vn"
LIST_PATH = "/lehoi/danhsach.aspx"
USER_AGENT = "TravelPlanner-FestivalImporter/1.0 (public-data research)"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "festivals.csv"


@dataclass(frozen=True)
class FestivalCategory:
    code: str
    label: str
    expected_pages: int


CATEGORIES = (
    FestivalCategory("LEHOITRUYENTHONG", "Lễ hội truyền thống", 518),
    FestivalCategory("LEHOIVANHOA", "Lễ hội văn hóa", 35),
    FestivalCategory("LEHOINGANHNGHE", "Lễ hội ngành nghề", 4),
    FestivalCategory(
        "LEHOICONGUONGOCTUNUOCNGOAI",
        "Lễ hội có nguồn gốc từ nước ngoài",
        1,
    ),
)

CATALOG_FIELDS = (
    "source_id",
    "name",
    "festival_type",
    "province_text",
    "venue_text",
    "source_url",
    "source_list_url",
    "retrieved_at",
)

DETAIL_FIELDS = (
    "organization_scale",
    "schedule_text",
    "district_text",
    "worship_subject",
    "ceremony_text",
    "festival_activities_text",
    "reference_text",
    "protection_measures_text",
    "registration_notice_text",
    "frequency_text",
    "catalog_year_text",
    "detail_retrieved_at",
)

DETAIL_LABELS = {
    "organization_scale": "Quy mô tổ chức",
    "schedule_text": "Thời gian tổ chức",
    "district_text": "Quận/Huyện",
    "worship_subject": "Đối tượng thờ phụng",
    "ceremony_text": "Phần lễ",
    "festival_activities_text": "Phần hội",
    "reference_text": "Tư liệu lễ hội",
    "protection_measures_text": "Biện pháp bảo vệ",
    "registration_notice_text": "Thời điểm đăng ký hoặc thông báo",
    "frequency_text": "Kỳ tổ chức",
    "catalog_year_text": "Năm đưa vào danh mục",
}

_thread_local = threading.local()


def normalized_text(value: str | None) -> str:
    return " ".join((value or "").split())


def session() -> requests.Session:
    current = getattr(_thread_local, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5",
            }
        )
        _thread_local.session = current
    return current


def fetch(url: str, *, attempts: int = 4) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session().get(url, timeout=(10, 30))
            response.raise_for_status()
            # The portal serves UTF-8 HTML. Avoid requests.apparent_encoding:
            # charset detection is disproportionately slow on these pages.
            response.encoding = "utf-8"
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def list_url(category: FestivalCategory, page_number: int) -> str:
    return (
        f"{BASE_URL}{LIST_PATH}?pageid=5018&month=&action=&quymo=&disan="
        f"&type={category.code}&pagenumber={page_number}"
    )


def parse_catalog_page(
    html: str,
    *,
    category: FestivalCategory,
    page_url: str,
    retrieved_at: str,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, str]] = []

    for heading in soup.select("h3.article-title"):
        anchor = heading.find("a", href=re.compile(r"/lehoi/detail\.aspx\?id=\d+"))
        container = heading.find_parent("div", class_="info-article-full")
        if anchor is None or container is None:
            continue

        detail_url = urljoin(BASE_URL, anchor.get("href", ""))
        source_ids = parse_qs(urlparse(detail_url).query).get("id", [])
        if not source_ids:
            continue

        metadata = [
            normalized_text(item.get_text(" ", strip=True))
            for item in container.select(".detail-muted li")
        ]
        records.append(
            {
                "source_id": source_ids[0],
                "name": normalized_text(anchor.get_text(" ", strip=True)),
                "festival_type": metadata[1] if len(metadata) > 1 else category.label,
                "province_text": metadata[0] if metadata else "",
                "venue_text": metadata[2] if len(metadata) > 2 else "",
                "source_url": detail_url,
                "source_list_url": page_url,
                "retrieved_at": retrieved_at,
            }
        )
    return records


def import_catalog(
    *,
    pause_seconds: float,
    max_pages_per_category: int | None = None,
) -> list[dict[str, str]]:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    by_id: dict[str, dict[str, str]] = {}
    total_pages = sum(category.expected_pages for category in CATEGORIES)
    completed_pages = 0

    for category in CATEGORIES:
        category_pages = category.expected_pages
        if max_pages_per_category is not None:
            category_pages = min(category_pages, max_pages_per_category)
        for page_number in range(1, category_pages + 1):
            url = list_url(category, page_number)
            if completed_pages == 0:
                print(f"Fetching first catalog page: {url}", flush=True)
            response = fetch(url)
            for record in parse_catalog_page(
                response.text,
                category=category,
                page_url=url,
                retrieved_at=retrieved_at,
            ):
                by_id[record["source_id"]] = record

            completed_pages += 1
            if completed_pages == 1 or completed_pages % 25 == 0:
                print(
                    f"Catalog pages: {completed_pages}/{total_pages}; "
                    f"unique records: {len(by_id)}",
                    flush=True,
                )
            if pause_seconds:
                time.sleep(pause_seconds)

    return sorted(by_id.values(), key=lambda row: int(row["source_id"]))


def detail_table(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        index = 0
        while index + 1 < len(cells):
            label = normalized_text(cells[index].get_text(" ", strip=True))
            value = normalized_text(cells[index + 1].get_text(" ", strip=True))
            if label:
                result[label] = "" if value == "Không có thông tin" else value
            index += 2
    return result


def enrich_one(record: dict[str, str], *, pause_seconds: float) -> dict[str, str]:
    response = fetch(record["source_url"])
    table = detail_table(response.text)
    enriched = dict(record)
    for field, label in DETAIL_LABELS.items():
        enriched[field] = table.get(label, "")
    enriched["detail_retrieved_at"] = datetime.now(timezone.utc).isoformat()
    if pause_seconds:
        time.sleep(pause_seconds)
    return enriched


def enrich_details(
    records: Iterable[dict[str, str]],
    *,
    workers: int,
    pause_seconds: float,
) -> list[dict[str, str]]:
    source = list(records)
    source_by_id = {row["source_id"]: row for row in source}
    enriched: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                enrich_one,
                record,
                pause_seconds=pause_seconds,
            ): record["source_id"]
            for record in source
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            source_id = futures[future]
            try:
                enriched.append(future.result())
            except Exception as exc:
                print(f"Detail failed for source_id={source_id}: {exc}", file=sys.stderr)
                fallback = source_by_id[source_id]
                enriched.append({**fallback, **dict.fromkeys(DETAIL_FIELDS, "")})
            if completed == 1 or completed % 100 == 0:
                print(f"Detail pages: {completed}/{len(source)}", flush=True)
    return sorted(enriched, key=lambda row: int(row["source_id"]))


def write_csv(path: Path, records: list[dict[str, str]], *, details: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = CATALOG_FIELDS + (DETAIL_FIELDS if details else ())
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(path)


def write_metadata(path: Path, records: list[dict[str, str]], *, details: bool) -> None:
    counts: dict[str, int] = {}
    for record in records:
        festival_type = record["festival_type"]
        counts[festival_type] = counts.get(festival_type, 0) + 1

    metadata = {
        "dataset": path.name,
        "recordCount": len(records),
        "festivalTypeCounts": dict(sorted(counts.items())),
        "source": BASE_URL,
        "sourcePublisher": "Cục Văn hóa cơ sở, Gia đình và Thư viện",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "detailEnrichment": details,
        "dataQuality": {
            "missingNameCount": sum(not row["name"] for row in records),
            "missingProvinceCount": sum(not row["province_text"] for row in records),
            "missingVenueCount": sum(not row["venue_text"] for row in records),
            "duplicateSourceIdCount": len(records)
            - len({row["source_id"] for row in records}),
        },
        "licenseNote": (
            "Publicly accessible government portal; verify reuse and attribution "
            "requirements before redistribution."
        ),
        "freshnessNote": (
            "This is a festival inventory. schedule_text is a customary schedule, "
            "not confirmation that an occurrence will run in a specific year."
        ),
    }
    path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--details",
        action="store_true",
        help="Fetch every detail page and include schedule/activities.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent detail requests; constrained to 1..8.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.15,
        help="Polite pause after each request in a worker.",
    )
    parser.add_argument(
        "--max-pages-per-category",
        type=int,
        help="Development-only limit for parser/network smoke tests.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        help="Development-only record limit applied before detail enrichment.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("--workers must be between 1 and 8")
    if args.pause_seconds < 0:
        raise SystemExit("--pause-seconds must be non-negative")

    records = import_catalog(
        pause_seconds=args.pause_seconds,
        max_pages_per_category=args.max_pages_per_category,
    )
    if args.max_records is not None:
        if args.max_records < 1:
            raise SystemExit("--max-records must be positive")
        records = records[: args.max_records]
    if args.details:
        records = enrich_details(
            records,
            workers=args.workers,
            pause_seconds=args.pause_seconds,
        )
    write_csv(args.output, records, details=args.details)
    write_metadata(args.output, records, details=args.details)
    print(f"Wrote {len(records)} records to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
