from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Iterable

from .models import SourceRecord, utc_now


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")
    return cleaned[:80] or "record"


class DatasetStore:
    def __init__(self, root: Path, *, save_raw: bool = True) -> None:
        self.root = root
        self.raw_root = root / "raw"
        self.normalized_root = root / "normalized"
        self.save_raw_enabled = save_raw
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.normalized_root.mkdir(parents=True, exist_ok=True)

    def save_raw(
        self,
        *,
        source: str,
        url: str,
        content: bytes,
        content_type: str,
        status_code: int,
        headers: dict[str, str],
    ) -> str | None:
        if not self.save_raw_enabled:
            return None
        digest = hashlib.sha256(content).hexdigest()
        source_dir = self.raw_root / _safe_name(source)
        source_dir.mkdir(parents=True, exist_ok=True)
        data_path = source_dir / f"{digest}.bin.gz"
        if not data_path.exists():
            with gzip.open(data_path, "wb") as handle:
                handle.write(content)
        manifest_path = source_dir / "manifest.jsonl"
        manifest_item = {
            "url": url,
            "statusCode": status_code,
            "contentType": content_type,
            "contentSha256": digest,
            "retrievedAt": utc_now(),
            "headers": {
                key: value
                for key, value in headers.items()
                if key.lower() in {"content-type", "etag", "last-modified", "content-language"}
            },
            "file": data_path.name,
        }
        with manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest_item, ensure_ascii=False) + "\n")
        return str(data_path)

    def load_records(self, source: str) -> dict[str, SourceRecord]:
        path = self.normalized_root / f"{_safe_name(source)}.jsonl"
        records: dict[str, SourceRecord] = {}
        if not path.exists():
            return records
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = SourceRecord.from_dict(json.loads(line))
                    records[record.record_id] = record
        return records

    def merge_records(self, source: str, incoming: Iterable[SourceRecord]) -> tuple[Path, int]:
        records = self.load_records(source)
        for record in incoming:
            records[record.record_id] = record
        path = self.normalized_root / f"{_safe_name(source)}.jsonl"
        tmp_path = path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record_id in sorted(records):
                handle.write(json.dumps(records[record_id].to_dict(), ensure_ascii=False) + "\n")
        for attempt in range(3):
            try:
                os.replace(tmp_path, path)
                break
            except PermissionError:
                if attempt == 2:
                    # Windows indexers/antivirus can briefly hold the target.
                    # Preserve the completed temp file and copy its bytes as a
                    # final fallback instead of discarding the fetched batch.
                    shutil.copyfile(tmp_path, path)
                    tmp_path.unlink(missing_ok=True)
                    break
                time.sleep(0.5 * (attempt + 1))
        return path, len(records)
