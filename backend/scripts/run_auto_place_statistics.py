from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService
from app.modules.places.repository import SqlAlchemyPlaceRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh automatic Place statistics when places.csv changes."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "database" / "generated" / "place_region_statistics.json",
        help="Generated statistics JSON.",
    )
    parser.add_argument(
        "--stale-after-days",
        type=int,
        default=30,
        help="Operational data age considered stale.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalculate even when the source fingerprint is unchanged.",
    )
    parser.add_argument(
        "--region-key",
        help="Planner region scope, for example vn,ha-noi.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as session:
        service = AutoPlaceStatisticsService(
            SqlAlchemyPlaceRepository(session),
            args.output,
            stale_after_days=args.stale_after_days,
        )
        if args.region_key:
            planner_result = service.get_for_planner(
                args.region_key,
                force=args.force,
            )
            output = {
                "status": planner_result.status,
                "requestedRegionKey": planner_result.region_key,
                "snapshotId": planner_result.snapshot_id,
                "catalogVersion": planner_result.catalog_version,
                "regionCount": len(planner_result.regions),
                "sourceFingerprint": planner_result.source_fingerprint,
            }
        else:
            result = service.refresh(force=args.force)
            output = {
                "status": result.status,
                "outputPath": str(result.output_path),
                "sourceRowCount": result.source_row_count,
                "regionCount": result.region_count,
                "sourceFingerprint": result.source_fingerprint,
            }
    print(
        json.dumps(
            output,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
