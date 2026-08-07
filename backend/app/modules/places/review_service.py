from app.modules.places.review_repository import PlaceReviewRepository
from app.modules.places.review_schema import PlaceReviewPage, PlaceReviewRead


class PlaceReviewService:
    def __init__(self, repository: PlaceReviewRepository) -> None:
        self.repository = repository

    def list_reviews(
        self,
        entity_id: str,
        *,
        rating: int | None,
        limit: int,
        offset: int,
    ) -> PlaceReviewPage:
        items, total = self.repository.list_for_entity(
            entity_id,
            rating=rating,
            limit=limit,
            offset=offset,
        )
        return PlaceReviewPage(
            items=[
                PlaceReviewRead(
                    id=item.id,
                    authorName=item.author_name,
                    rating=item.rating,
                    publishedAt=item.published_at,
                    whenText=item.when_text,
                    language=item.language,
                    reviewText=item.review_text,
                )
                for item in items
            ],
            total=total,
            limit=limit,
            offset=offset,
            hasMore=offset + len(items) < total,
            ratingCounts=self.repository.rating_counts(entity_id),
        )
