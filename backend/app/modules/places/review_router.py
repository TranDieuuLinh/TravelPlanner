from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.places.review_repository import SqlAlchemyPlaceReviewRepository
from app.modules.places.review_schema import PlaceReviewPage
from app.modules.places.review_service import PlaceReviewService


router = APIRouter(prefix="/places", tags=["places"])


def get_place_review_service(
    db: Annotated[Session, Depends(get_db)],
) -> PlaceReviewService:
    return PlaceReviewService(SqlAlchemyPlaceReviewRepository(db))


@router.get("/{entity_id}/reviews", response_model=PlaceReviewPage)
def list_place_reviews(
    entity_id: Annotated[str, Path(min_length=1, max_length=96)],
    service: Annotated[PlaceReviewService, Depends(get_place_review_service)],
    rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlaceReviewPage:
    return service.list_reviews(
        entity_id,
        rating=rating,
        limit=limit,
        offset=offset,
    )
