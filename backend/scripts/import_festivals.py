"""Import festivals from CSV to PostgreSQL.

Usage:
    python -m scripts.import_festivals
"""
from __future__ import annotations

import csv
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.modules.places.model import Festival


# CSV column mapping
CSV_COLUMNS = [
    "source_id",
    "source_url",
    "name",
    "venue",
    "scale_level",
    "timing",
    "province",
    "district",
    "deity",
    "ceremony_part",
    "festival_part",
    "festival_type",
    "documentation",
    "protection_measure",
    "registration_time",
    "recurrence",
    "listed_year",
]

# The repository's current catalog CSV uses stable English field names while
# older exports used Vietnamese display labels. Keep both shapes importable so
# refreshing the catalog does not silently skip every row.
CSV_COLUMN_ALIASES = {
    "source_id": ("source_id",),
    "source_url": ("source_url",),
    "name": ("name", "Tên lễ hội"),
    "venue": ("venue_text", "venue", "Địa điểm tổ chức"),
    "scale_level": ("organization_scale", "scale_level", "Quy mô tổ chức"),
    "timing": ("schedule_text", "timing", "Thời gian tổ chức"),
    "province": ("province_text", "province", "Tỉnh/Thành phố"),
    "district": ("district_text", "district", "Quận/Huyện"),
    "deity": ("worship_subject", "deity", "Đối tượng thờ phụng"),
    "ceremony_part": ("ceremony_text", "ceremony_part", "Phần lễ"),
    "festival_part": (
        "festival_activities_text",
        "festival_part",
        "Phần hội",
    ),
    "festival_type": ("festival_type", "Loại lễ hội"),
    "documentation": ("reference_text", "documentation", "Tư liệu lễ hội"),
    "protection_measure": (
        "protection_measures_text",
        "protection_measure",
        "Biện pháp bảo vệ",
    ),
    "registration_time": (
        "registration_notice_text",
        "registration_time",
        "Thời điểm đăng ký hoặc thông báo",
    ),
    "recurrence": ("frequency_text", "recurrence", "Kỳ tổ chức"),
    "listed_year": ("catalog_year_text", "listed_year", "Năm đưa vào danh mục"),
}

# Scale level mapping from Vietnamese to internal codes
SCALE_MAPPING = {
    "cấp quốc gia": "quoc-gia",
    "cấp vùng": "vung",
    "cấp tỉnh": "tinh",
    "cấp huyện": "huyen",
    "cấp xã": "xa",
}


def normalize_scale(scale_str: str | None) -> str:
    """Normalize scale level to internal code."""
    if not scale_str:
        return "dia-phuong"
    scale_str = scale_str.strip().lower()
    return SCALE_MAPPING.get(scale_str, "dia-phuong")


def parse_listed_year(value: str | None) -> int | None:
    """Parse listed year from string."""
    if not value:
        return None
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return None


def normalize_csv_row(csv_row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for target, aliases in CSV_COLUMN_ALIASES.items():
        normalized[target] = next(
            (
                str(csv_row.get(alias) or "").strip()
                for alias in aliases
                if str(csv_row.get(alias) or "").strip()
            ),
            "",
        )
    normalized["source_list_url"] = str(csv_row.get("source_list_url") or "").strip()
    normalized["retrieved_at"] = str(csv_row.get("retrieved_at") or "").strip()
    normalized["detail_retrieved_at"] = str(
        csv_row.get("detail_retrieved_at") or ""
    ).strip()
    return normalized


def row_to_festival(row: dict) -> dict:
    """Convert a CSV row dict to Festival kwargs."""
    return {
        "id": str(uuid.uuid4()),
        "source_id": row.get("source_id", "").strip(),
        "source_url": row.get("source_url", "").strip() or None,
        "name": row.get("name", "").strip(),
        "venue": row.get("venue", "").strip() or None,
        "scale_level": normalize_scale(row.get("scale_level")),
        "timing": row.get("timing", "").strip() or None,
        "province": row.get("province", "").strip() or None,
        "district": row.get("district", "").strip() or None,
        "deity": row.get("deity", "").strip() or None,
        "ceremony_part": row.get("ceremony_part", "").strip() or None,
        "festival_part": row.get("festival_part", "").strip() or None,
        "festival_type": row.get("festival_type", "").strip() or None,
        "documentation": row.get("documentation", "").strip() or None,
        "protection_measure": row.get("protection_measure", "").strip() or None,
        "registration_time": row.get("registration_time", "").strip() or None,
        "recurrence": row.get("recurrence", "").strip() or None,
        "listed_year": parse_listed_year(row.get("listed_year")),
        "metadata_json": {
            key: value
            for key, value in {
                "sourceListUrl": row.get("source_list_url") or None,
                "retrievedAt": row.get("retrieved_at") or None,
                "detailRetrievedAt": row.get("detail_retrieved_at") or None,
            }.items()
            if value is not None
        },
    }


def truncate_festivals() -> None:
    """Truncate the festivals table."""
    db: Session = SessionLocal()
    try:
        db.execute(text("TRUNCATE festivals RESTART IDENTITY CASCADE"))
        db.commit()
    finally:
        db.close()


def import_festivals(csv_path: str | Path, batch_size: int = 500, truncate: bool = False) -> tuple[int, int]:
    """Import festivals from CSV file.

    Returns:
        Tuple of (inserted_count, skipped_count)
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    db: Session = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        batch = []

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for csv_row in reader:
                row = normalize_csv_row(csv_row)
                festival_data = row_to_festival(row)

                # Skip rows with empty source_id or name
                if not festival_data["source_id"] or not festival_data["name"]:
                    skipped += 1
                    continue

                batch.append(Festival(**festival_data))

                if len(batch) >= batch_size:
                    db.bulk_save_objects(batch)
                    db.commit()
                    inserted += len(batch)
                    batch = []

            # Insert remaining
            if batch:
                db.bulk_save_objects(batch)
                db.commit()
                inserted += len(batch)

        return inserted, skipped

    finally:
        db.close()


def get_province_stats() -> list[dict]:
    """Get statistics by province."""
    db: Session = SessionLocal()
    try:
        result = db.execute(
            text("""
                SELECT province, COUNT(*) as count
                FROM festivals
                WHERE province IS NOT NULL
                GROUP BY province
                ORDER BY count DESC
                LIMIT 20
            """)
        )
        return [{"province": row[0], "count": row[1]} for row in result.fetchall()]
    finally:
        db.close()


def get_scale_stats() -> list[dict]:
    """Get statistics by scale level."""
    db: Session = SessionLocal()
    try:
        result = db.execute(
            text("""
                SELECT scale_level, COUNT(*) as count
                FROM festivals
                GROUP BY scale_level
                ORDER BY count DESC
            """)
        )
        return [{"scale_level": row[0], "count": row[1]} for row in result.fetchall()]
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import festivals from CSV")
    parser.add_argument(
        "--csv",
        type=str,
        default="K:/travelplanner/auto-crawl/festival-detail.csv",
        help="Path to CSV file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for bulk insert",
    )
    args = parser.parse_args()

    print(f"Importing festivals from: {args.csv}")
    print(f"Batch size: {args.batch_size}")

    inserted, skipped = import_festivals(args.csv, args.batch_size)
    print(f"\nDone! Inserted: {inserted}, Skipped: {skipped}")

    # Show stats
    print("\nBy Province (top 20):")
    for stat in get_province_stats():
        print(f"  {stat['province']}: {stat['count']}")

    print("\nBy Scale Level:")
    for stat in get_scale_stats():
        print(f"  {stat['scale_level']}: {stat['count']}")
