"""Reconcile Hanoi food/drink specialties; defaults to a rolled-back dry run."""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.modules.knowledge_graph.tagging.specialty_food_catalog import (
    HanoiSpecialtyFoodCatalogService,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            summary = HanoiSpecialtyFoodCatalogService(db).reconcile()
            if args.apply:
                db.commit()
            else:
                db.rollback()
            summary["mode"] = "apply" if args.apply else "dry-run"
            if not args.verbose:
                summary.pop("changes", None)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
