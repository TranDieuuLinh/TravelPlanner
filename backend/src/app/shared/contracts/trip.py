from pydantic import BaseModel, Field


class TripIntent(BaseModel):
    destination: str = Field(min_length=1, max_length=120)
    days: int = Field(default=1, ge=1, le=30)
    budget: float | None = Field(default=None, ge=0)
    people: int = Field(default=1, ge=1, le=100)
    preferences: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)
