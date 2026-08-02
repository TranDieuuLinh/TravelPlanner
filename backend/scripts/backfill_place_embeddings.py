from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integrations.embeddings import GeminiEmbeddingClient  # noqa: E402
from app.modules.places.model import Place  # noqa: E402
from app.modules.places.repository import SqlAlchemyPlaceRepository  # noqa: E402
from app.modules.places.semantic import (  # noqa: E402
    build_place_embedding_text,
    place_embedding_content_hash,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill semantic embeddings for active catalog places."
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--region-key", default="vn,ha-noi")
    scope.add_argument(
        "--all-regions",
        action="store_true",
        help="Backfill every active place regardless of region_key.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--commit-every", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=2.0,
        help="Global request start rate across all workers (default: 2).",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.limit < 1
        or args.commit_every < 1
        or args.workers < 1
        or args.requests_per_second <= 0
    ):
        raise SystemExit(
            "--limit, --commit-every, --workers and --requests-per-second "
            "must be positive"
        )
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required for embedding backfill")

    client = GeminiEmbeddingClient(
        settings.gemini_api_key,
        model=settings.gemini_embedding_model,
        dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_embedding_timeout_seconds,
        min_interval_seconds=1.0 / args.requests_per_second,
    )
    region_key = None if args.all_regions else args.region_key
    with SessionLocal() as session:
        repository = SqlAlchemyPlaceRepository(session)
        places = repository.list_places_needing_embeddings(
            region_key,
            embedding_model=client.model,
            limit=args.limit,
        )
        print(
            f"Selected {len(places)} places in {region_key or 'all regions'} "
            f"for {client.model}/{client.dimensions}."
        )
        if args.dry_run:
            return 0
        pending = [
            (
                place.id,
                place.name,
                build_place_embedding_text(place),
                place_embedding_content_hash(place),
            )
            for place in places
            if not (
                place.embedding is not None
                and place.embedding_model == client.model
                and place.embedding_content_hash == place_embedding_content_hash(place)
            )
        ]
        # Keep only immutable scalar snapshots across commits. ORM instances are
        # expired by commit and catalog import jobs may refresh them independently.
        session.expunge_all()
        completed = 0
        failures = 0
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for batch_start in range(0, len(pending), args.commit_every):
                batch = pending[batch_start : batch_start + args.commit_every]
                futures = [
                    executor.submit(
                        client.embed_document,
                        text,
                        title=place_name,
                    )
                    for _, place_name, text, _ in batch
                ]
                for (place_id, _, _, content_hash), future in zip(batch, futures):
                    try:
                        embedding = future.result()
                    except Exception:
                        failures += 1
                        continue
                    embedded_at = datetime.now(timezone.utc)
                    result = session.execute(
                        Place.__table__.update()
                        .where(Place.__table__.c.id == place_id)
                        .values(
                            embedding=embedding,
                            embedding_model=client.model,
                            embedding_content_hash=content_hash,
                            embedded_at=embedded_at,
                            # SQLAlchemy's column-level onupdate would otherwise
                            # make updated_at a few microseconds newer and mark
                            # the freshly written vector stale immediately.
                            updated_at=embedded_at,
                        )
                    )
                    if result.rowcount != 1:
                        failures += 1
                        continue
                    completed += 1
                session.commit()
                print(
                    f"Embedded {completed}/{len(pending)} places "
                    f"({failures} failed)."
                )
        session.commit()
        print(f"Embedded {completed} places successfully; {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
