from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integrations.embeddings import GeminiEmbeddingClient  # noqa: E402
from app.modules.places.repository import SqlAlchemyPlaceRepository  # noqa: E402
from app.modules.plans.finder.place_tool import RepositoryFinderPlaceTool  # noqa: E402


QUERIES = {
    "traditional_hanoi_food": [
        "local food",
        "traditional Hanoi cuisine",
        "món ăn đặc trưng Hà Nội",
    ],
    "history_and_culture": [
        "Hanoi history and culture",
        "heritage architecture museum",
        "di sản lịch sử Hà Nội",
    ],
    "local_coffee": [
        "local Hanoi coffee",
        "Vietnamese traditional coffee experience",
        "cà phê trứng Hà Nội",
    ],
}


def main() -> int:
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required")
    embedding_client = GeminiEmbeddingClient(
        settings.gemini_api_key,
        model=settings.gemini_embedding_model,
        dimensions=settings.gemini_embedding_dimensions,
        timeout_seconds=settings.gemini_embedding_timeout_seconds,
    )
    with SessionLocal() as session:
        tool = RepositoryFinderPlaceTool(
            SqlAlchemyPlaceRepository(session),
            embedding_client,
        )
        for label, tags in QUERIES.items():
            print(f"\n=== {label} ===")
            results = tool.search(
                region_key="vn,ha-noi",
                target_tags=tags,
                excluded_place_ids=set(),
                limit=10,
            )
            for rank, place in enumerate(results, start=1):
                print(
                    f"{rank:>2}. {place.name} | {place.place_type} | "
                    f"rating={place.rating} reviews={place.review_count} | "
                    f"{place.region_key}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
