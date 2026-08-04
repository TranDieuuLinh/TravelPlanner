"""Import festivals from CSV to PostgreSQL using COPY command.

This script uses psql COPY for fast bulk import.
"""
from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path


def escape_sql_string(value: str | None) -> str:
    """Escape a string value for SQL."""
    if value is None:
        return r'\N'
    # Escape backslashes first, then single quotes
    escaped = value.replace('\\', '\\\\').replace("'", "''")
    return escaped


def format_row(row: dict) -> str:
    """Format a CSV row for PostgreSQL COPY format."""
    fields = [
        str(uuid.uuid4()),  # id
        row.get('source_id', '').strip() or r'\N',  # source_id
        row.get('source_url', '').strip() or r'\N',  # source_url
        row.get('Tên lễ hội', '').strip() or r'\N',  # name
        row.get('Địa điểm tổ chức', '').strip() or r'\N',  # venue
        row.get('Quy mô tổ chức', '').strip() or r'\N',  # scale_level
        row.get('Thời gian tổ chức', '').strip() or r'\N',  # timing
        row.get('Tỉnh/Thành phố', '').strip() or r'\N',  # province
        row.get('Quận/Huyện', '').strip() or r'\N',  # district
        row.get('Đối tượng thờ phụng', '').strip() or r'\N',  # deity
        row.get('Phần lễ', '').strip() or r'\N',  # ceremony_part
        row.get('Phần hội', '').strip() or r'\N',  # festival_part
        row.get('Loại lễ hội', '').strip() or r'\N',  # festival_type
        row.get('Tư liệu lễ hội', '').strip() or r'\N',  # documentation
        row.get('Biện pháp bảo vệ', '').strip() or r'\N',  # protection_measure
        row.get('Thời điểm đăng ký hoặc thông báo', '').strip() or r'\N',  # registration_time
        row.get('Kỳ tổ chức', '').strip() or r'\N',  # recurrence
        row.get('Năm đưa vào danh mục', '').strip() or r'\N',  # listed_year
        '{}',  # metadata (empty JSON)
        r'\N',  # created_at (will use DEFAULT)
        r'\N',  # updated_at (will use DEFAULT)
    ]
    return '\t'.join(escape_sql_string(f) for f in fields)


if __name__ == "__main__":
    import argparse
    import subprocess
    import sys

    parser = argparse.ArgumentParser(description="Import festivals from CSV using psql COPY")
    parser.add_argument(
        "--csv",
        type=str,
        default="K:/VSF/VSF_TravelPlanner/auto-crawl/festival-detail.csv",
        help="Path to CSV file",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="PostgreSQL host",
    )
    parser.add_argument(
        "--port",
        type=str,
        default="5432",
        help="PostgreSQL port",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    print(f"Reading CSV: {csv_path}")

    # Read and process CSV
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total rows: {len(rows)}")

    # Create COPY format data
    output = io.StringIO()
    for i, row in enumerate(rows):
        # Skip rows without source_id or name
        source_id = row.get('source_id', '').strip()
        name = row.get('Tên lễ hội', '').strip()
        if not source_id or not name:
            continue

        # Add UUID prefix to make unique id
        unique_id = str(uuid.uuid4())
        line = f"{unique_id}\t{format_row(row)[36:]}"  # Skip the id we regenerate
        output.write(line + '\n')

    output.seek(0)

    # Run psql COPY command
    copy_cmd = [
        "psql",
        "-h", args.host,
        "-p", args.port,
        "-U", "vsf",
        "-d", "vsf_travel",
        "-c",
        f"\\COPY festivals (id, source_id, source_url, name, venue, scale_level, timing, province, district, deity, ceremony_part, festival_part, festival_type, documentation, protection_measure, registration_time, recurrence, listed_year, metadata, created_at, updated_at) FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\\\N')"
    ]

    print("Importing to PostgreSQL...")
    result = subprocess.run(
        copy_cmd,
        input=output.getvalue(),
        capture_output=True,
        text=True,
        env={"PGPASSWORD": "vsf", **subprocess.os.environ}
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)

    print(result.stdout)
    print("Import completed!")
