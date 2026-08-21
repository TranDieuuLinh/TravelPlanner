from pydantic import Field

from app.modules.place_checker.contract import ContractModel


class SubplaceSummary(ContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=300)
    address: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    image_url: str | None = Field(default=None, max_length=2048)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    cost_per_person: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)


class SubplaceGroup(ContractModel):
    parent_place_id: str = Field(min_length=1, max_length=300)
    total_count: int = Field(ge=0)
    items: list[SubplaceSummary] = Field(default_factory=list, max_length=50)
