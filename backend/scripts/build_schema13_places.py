"""Build a schema-13-compatible places.csv from the external mock dataset."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_DIR = Path(r"K:\VSF\TravelPlanner\database_mock")
OUTPUT_FILE = Path(__file__).resolve().parents[2] / "database" / "places.csv"

OUTPUT_COLUMNS = [
    "id",
    "name",
    "place_type",
    "address",
    "city",
    "country",
    "country_code",
    "region_key",
    "primary_area",
    "latitude",
    "longitude",
    "status",
    "opening_hours",
    "typical_duration_minutes",
    "data_confidence",
    "source_fetched_at",
    "revision",
    "metadata",
    "deleted_at",
    "created_at",
    "updated_at",
]

ADMIN_PREFIXES = (
    "thanh-pho-",
    "thi-tran-",
    "thi-xa-",
    "tinh-",
    "quan-",
    "huyen-",
    "phuong-",
    "xa-",
)

STATUS_MAP = {
    "operating": "active",
    "active": "active",
    "temporarily_closed": "temporarily_closed",
    "permanently_closed": "permanently_closed",
    "closed": "permanently_closed",
}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def optional_json(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def optional_bool(value: str) -> bool | None:
    if not value:
        return None
    return value.strip().lower() in {"true", "1", "yes"}


def optional_int(value: str) -> int | None:
    if not value:
        return None
    return int(value)


def slugify_region_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().replace("Đ", "D").replace("đ", "d"))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    for prefix in ADMIN_PREFIXES:
        if slug.startswith(prefix):
            return slug[len(prefix) :]
    return slug


def build_region_key(row: dict[str, str]) -> str:
    parts = ["vn"]
    for field in ("province_city", "district", "subdistrict", "locality"):
        part = slugify_region_part(row.get(field, ""))
        if part and part not in parts:
            parts.append(part)
    return ",".join(parts)


def confidence_label(values: list[float]) -> str:
    if not values:
        return "low"
    score = sum(values) / len(values)
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def latest_timestamp(values: list[str], fallback: str) -> str:
    candidates = [value for value in values if value]
    return max(candidates) if candidates else fallback


def provenance_by_record() -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    with (SOURCE_DIR / "mock_provenance.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            result[(row["table_name"], row["record_id"])] = {
                "isMock": True,
                "ruleId": row["rule_id"],
                "confidence": float(row["confidence"]) if row["confidence"] else None,
                "generatedAt": row["generated_at"] or None,
                "notes": row["notes"] or None,
            }
    return result


def load_opening_hours(
    provenance: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with (SOURCE_DIR / "place_opening_hours.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            record = {
                "dayOfWeek": int(row["day_of_week"]),
                "openTime": row["open_time"] or None,
                "closeTime": row["close_time"] or None,
                "is24Hours": optional_bool(row["is_24_hours"]),
                "validFrom": row["valid_from"] or None,
                "validUntil": row["valid_until"] or None,
            }
            mock_info = provenance.get(("place_opening_hours", row["id"]))
            if mock_info:
                record["provenance"] = mock_info
            result[row["place_id"]].append(record)
    return result


def load_prices(
    provenance: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with (SOURCE_DIR / "place_prices.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            record = {
                "priceType": row["price_type"],
                "customerType": row["customer_type"] or None,
                "amountMin": optional_int(row["amount_min"]),
                "amountMax": optional_int(row["amount_max"]),
                "currency": row["currency"] or None,
                "unit": row["unit"] or None,
                "description": row["description"] or None,
                "validFrom": row["valid_from"] or None,
                "validUntil": row["valid_until"] or None,
                "isMock": row["description"].startswith("[MOCK ESTIMATE]"),
            }
            mock_info = provenance.get(("place_prices", row["id"]))
            if mock_info:
                record["provenance"] = mock_info
            result[row["place_id"]].append(record)
    return result


def load_special_hours(
    provenance: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with (SOURCE_DIR / "place_special_hours.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            record = {
                "date": row["date"],
                "status": row["status"],
                "openTime": row["open_time"] or None,
                "closeTime": row["close_time"] or None,
                "reason": row["reason"] or None,
            }
            mock_info = provenance.get(("place_special_hours", row["id"]))
            if mock_info:
                record["provenance"] = mock_info
            result[row["place_id"]].append(record)
    return result


def load_sources() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[float]], dict[str, list[str]]]:
    refs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    confidence: dict[str, list[float]] = defaultdict(list)
    fetched_at: dict[str, list[str]] = defaultdict(list)
    with (SOURCE_DIR / "place_sources.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            refs[row["place_id"]].append(
                {
                    "sourceName": row["source_name"],
                    "sourceUrl": row["source_url"] or None,
                    "externalId": row["external_id"] or None,
                    "retrievedAt": row["retrieved_at"] or None,
                    "lastVerifiedAt": row["last_verified_at"] or None,
                    "confidence": float(row["confidence"]) if row["confidence"] else None,
                }
            )
            if row["confidence"]:
                confidence[row["place_id"]].append(float(row["confidence"]))
            fetched_at[row["place_id"]].extend([row["retrieved_at"], row["last_verified_at"]])
    return refs, confidence, fetched_at


def build_metadata(
    row: dict[str, str],
    source_refs: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    special_hours: list[dict[str, Any]],
) -> dict[str, Any]:
    duration_min = optional_int(row["recommended_duration_min_minutes"])
    duration_max = optional_int(row["recommended_duration_max_minutes"])
    metadata: dict[str, Any] = {
        "description": row["description"] or None,
        "slug": row["slug"] or None,
        "placeGroup": row["place_group"] or None,
        "tags": optional_json(row["tags"]) or [],
        "attributes": optional_json(row["attributes"]) or {},
        "sourceRegionCode": row["region_code"] or None,
        "subdistrict": row["subdistrict"] or None,
        "locality": row["locality"] or None,
        "recommendedDurationRange": {
            "minMinutes": duration_min,
            "maxMinutes": duration_max,
        },
        "indoorOutdoor": row["indoor_outdoor"] or None,
        "weatherSensitivity": row["weather_sensitivity"] or None,
        "bookingRequired": optional_bool(row["booking_required"]),
        "phone": row["phone"] or None,
        "website": row["website"] or None,
        "prices": prices,
        "specialHours": special_hours,
        "sourceRefs": source_refs,
    }
    return metadata


def build() -> dict[str, Any]:
    provenance = provenance_by_record()
    opening_hours = load_opening_hours(provenance)
    prices = load_prices(provenance)
    special_hours = load_special_hours(provenance)
    source_refs, source_confidence, source_fetched_at = load_sources()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    seen_ids: set[str] = set()
    row_count = 0
    metadata_price_count = 0
    metadata_description_count = 0
    mock_price_count = 0

    with (
        (SOURCE_DIR / "places.csv").open(encoding="utf-8-sig", newline="") as input_file,
        OUTPUT_FILE.open("w", encoding="utf-8", newline="") as output_file,
    ):
        reader = csv.DictReader(input_file)
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for row in reader:
            place_id = row["id"]
            if place_id in seen_ids:
                raise ValueError(f"Duplicate place id: {place_id}")
            seen_ids.add(place_id)

            duration_min = optional_int(row["recommended_duration_min_minutes"])
            duration_max = optional_int(row["recommended_duration_max_minutes"])
            duration_values = [value for value in (duration_min, duration_max) if value is not None]
            typical_duration = round(sum(duration_values) / len(duration_values)) if duration_values else None

            place_prices = prices.get(place_id, [])
            metadata = build_metadata(
                row,
                source_refs.get(place_id, []),
                place_prices,
                special_hours.get(place_id, []),
            )
            if metadata["description"]:
                metadata_description_count += 1
            if place_prices:
                metadata_price_count += 1
                mock_price_count += sum(1 for price in place_prices if price["isMock"])

            primary_area = next(
                (
                    row[field]
                    for field in ("locality", "subdistrict", "district", "province_city")
                    if row.get(field)
                ),
                "",
            )
            fallback_timestamp = row["ingested_at"] or row["updated_at"] or row["created_at"]
            writer.writerow(
                {
                    "id": place_id,
                    "name": row["name"],
                    "place_type": row["place_type"],
                    "address": row["address"],
                    "city": row["province_city"],
                    "country": "Việt Nam",
                    "country_code": "VN",
                    "region_key": build_region_key(row),
                    "primary_area": primary_area,
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "status": STATUS_MAP.get(row["current_status"], "unverified"),
                    "opening_hours": compact_json(opening_hours.get(place_id, [])),
                    "typical_duration_minutes": typical_duration if typical_duration is not None else "",
                    "data_confidence": confidence_label(source_confidence.get(place_id, [])),
                    "source_fetched_at": latest_timestamp(
                        source_fetched_at.get(place_id, []),
                        fallback_timestamp,
                    ),
                    "revision": 1,
                    "metadata": compact_json(metadata),
                    "deleted_at": "",
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
            row_count += 1

    return {
        "output": str(OUTPUT_FILE),
        "rows": row_count,
        "uniqueIds": len(seen_ids),
        "columns": len(OUTPUT_COLUMNS),
        "descriptionsInMetadata": metadata_description_count,
        "placesWithPricesInMetadata": metadata_price_count,
        "mockPriceRecords": mock_price_count,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    print(compact_json(build()))
