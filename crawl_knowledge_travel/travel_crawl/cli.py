from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .collectors import COLLECTOR_TYPES
from .http_client import PoliteHttpClient
from .storage import DatasetStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect real travel source data; does not build a graph.")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=[*COLLECTOR_TYPES, "all"],
        default=["all"],
        help="Sources to collect. Default: all.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Dataset output directory.",
    )
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=500,
        help="Maximum normalized records per source; 0 means no limit.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Minimum delay per host in seconds; an additional 0-0.5s jitter is applied.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    parser.add_argument("--no-raw", action="store_true", help="Do not save compressed raw responses.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    selected = list(COLLECTOR_TYPES) if "all" in args.sources else args.sources
    store = DatasetStore(args.output.resolve(), save_raw=not args.no_raw)
    failures = 0
    with PoliteHttpClient(delay_seconds=args.delay, timeout_seconds=args.timeout) as client:
        for source in selected:
            collector = COLLECTOR_TYPES[source](client, store, limit=args.limit_per_source)
            logging.info("Collecting %s", source)
            try:
                records = collector.collect()
                path, total = store.merge_records(source, records)
                logging.info("%s: fetched %d records; dataset now has %d at %s", source, len(records), total, path)
            except Exception:
                failures += 1
                logging.exception("Collector %s failed", source)
    return 1 if failures else 0
