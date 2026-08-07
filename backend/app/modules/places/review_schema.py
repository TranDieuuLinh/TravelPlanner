from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return "".join([head, *(part.title() for part in tail)])


class PlaceReviewRead(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    id: str
    author_name: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    published_at: datetime | None = None
    when_text: str | None = None
    language: str | None = None
    review_text: str | None = None


class PlaceReviewPage(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    items: list[PlaceReviewRead]
    total: int
    limit: int
    offset: int
    has_more: bool
    rating_counts: dict[str, int]
