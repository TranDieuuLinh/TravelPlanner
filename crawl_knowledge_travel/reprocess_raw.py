from __future__ import annotations

import gzip
import json
from pathlib import Path

from travel_crawl.collectors import (
    VietnamTravelCollector,
    WikidataCollector,
    _html_record,
    wikidata_record_from_binding,
)
from travel_crawl.http_client import FetchResult
from travel_crawl.storage import DatasetStore


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def raw_entries(source: str):
    source_dir = DATA / "raw" / source
    manifest = source_dir / "manifest.jsonl"
    if not manifest.exists():
        return
    for line in manifest.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("statusCode") != 200:
            continue
        path = source_dir / item["file"]
        if not path.exists():
            continue
        with gzip.open(path, "rb") as handle:
            yield item, handle.read()


def rebuild_vietnam_travel(store: DatasetStore) -> int:
    records = {}
    for item, content in raw_entries("vietnam_travel") or []:
        url = item["url"]
        if not any(marker in url.casefold() for marker in VietnamTravelCollector.relevant_markers):
            continue
        record = _html_record(
            source="vietnam_travel",
            license_name="official-reference",
            result=FetchResult(
                url=url,
                status_code=200,
                content=content,
                headers={"content-type": item.get("contentType", "text/html")},
            ),
            record_type="official_travel_article",
        )
        if record:
            records[record.record_id] = record
    _, total = store.merge_records("vietnam_travel", records.values())
    return total


def rebuild_wikidata(store: DatasetStore) -> int:
    type_to_group = {
        qid: group
        for group, qids in WikidataCollector.ROOT_TYPES.items()
        for qid in qids
    }
    records = {}
    for _item, content in raw_entries("wikidata") or []:
        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        for binding in data.get("results", {}).get("bindings", []):
            type_url = binding.get("type", {}).get("value", "")
            group = type_to_group.get(type_url.rsplit("/", 1)[-1])
            if not group or "item" not in binding:
                continue
            record = wikidata_record_from_binding(binding, group)
            records[record.record_id] = record
    _, total = store.merge_records("wikidata", records.values())
    return total


def main() -> None:
    store = DatasetStore(DATA, save_raw=False)
    print(f"vietnam_travel: {rebuild_vietnam_travel(store)} records")
    print(f"wikidata: {rebuild_wikidata(store)} records")


if __name__ == "__main__":
    main()
