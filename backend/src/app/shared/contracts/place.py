from pydantic import BaseModel, Field, model_validator


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PlaceCandidate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source: str = "user"
    source_url: str | None = None
    coordinates: Coordinates | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)


class VerifiedPlace(BaseModel):
    place_id: str
    name: str
    coordinates: Coordinates
    source: str
    verified: bool = True
    estimated_visit_minutes: int = Field(default=90, ge=15, le=720)
    estimated_cost: float = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity_is_present(self) -> "VerifiedPlace":
        if not self.place_id.strip() or not self.name.strip():
            raise ValueError("place_id and name must not be blank")
        return self
