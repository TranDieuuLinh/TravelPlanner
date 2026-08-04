#!/usr/bin/env python3
"""Create an explicitly development-only GTFS copy with shifted service dates."""

from __future__ import annotations

import argparse
import csv
import io
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", default="20250101")
    parser.add_argument("--end", default="20291231")
    args = parser.parse_args()

    with zipfile.ZipFile(args.source) as source_zip:
        calendar_text = source_zip.read("calendar.txt").decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(calendar_text))
        rows = list(reader)
        if not reader.fieldnames:
            raise ValueError("calendar.txt has no header")
        for row in rows:
            row["start_date"] = args.start
            row["end_date"] = args.end

        calendar_output = io.StringIO(newline="")
        writer = csv.DictWriter(
            calendar_output,
            fieldnames=reader.fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            args.output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as output_zip:
            for info in source_zip.infolist():
                content = source_zip.read(info.filename)
                if info.filename == "calendar.txt":
                    content = calendar_output.getvalue().encode("utf-8")
                output_zip.writestr(info, content)

    print(
        "Created DEVELOPMENT-ONLY GTFS with shifted service dates: "
        f"{args.output} ({args.start}..{args.end})"
    )


if __name__ == "__main__":
    main()
