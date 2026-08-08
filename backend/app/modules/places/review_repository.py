from typing import Protocol

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.places.model import PlaceReview


class PlaceReviewRepository(Protocol):
    def list_for_entity(
        self,
        entity_id: str,
        *,
        rating: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PlaceReview], int]: ...

    def rating_counts(self, entity_id: str) -> dict[str, int]: ...


class SqlAlchemyPlaceReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_entity(
        self,
        entity_id: str,
        *,
        rating: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PlaceReview], int]:
        filters = [PlaceReview.entity_id == entity_id]
        if rating is not None:
            filters.append(PlaceReview.rating == rating)

        total = int(
            self.session.scalar(
                select(func.count(PlaceReview.id)).where(*filters)
            )
            or 0
        )
        items = list(
            self.session.scalars(
                select(PlaceReview)
                .where(*filters)
                .order_by(
                    case((PlaceReview.published_at.is_(None), 1), else_=0),
                    PlaceReview.published_at.desc(),
                    PlaceReview.created_at.desc(),
                    PlaceReview.id,
                )
                .offset(offset)
                .limit(limit)
            )
        )
        return items, total

    def rating_counts(self, entity_id: str) -> dict[str, int]:
        rows = self.session.execute(
            select(PlaceReview.rating, func.count(PlaceReview.id))
            .where(
                PlaceReview.entity_id == entity_id,
                PlaceReview.rating.between(1, 5),
            )
            .group_by(PlaceReview.rating)
        )
        counts = {str(star): 0 for star in range(1, 6)}
        for rating, count in rows:
            counts[str(rating)] = int(count)
        return counts
