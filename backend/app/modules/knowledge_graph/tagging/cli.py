"""CLI for the full Knowledge Graph place-tag scan."""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.modules.knowledge_graph.tagging.service import PlaceTaggingService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            summary = PlaceTaggingService(db).run(
                apply=args.apply,
                run_id=args.run_id,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
