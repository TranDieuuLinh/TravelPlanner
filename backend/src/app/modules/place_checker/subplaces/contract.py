from typing import Literal

from pydantic import Field

from app.modules.place_checker.contract import ContractModel


class SubplaceOfferItemContext(ContractModel):
    relationship_type: Literal["Offer_Item"] = "Offer_Item"
    activity_item_id: str = Field(min_length=1, max_length=300)
    activity_item_name: str = Field(min_length=1, max_length=300)
    action: str | None = Field(default=None, max_length=80)
    display_template: str | None = Field(default=None, max_length=500)


class SubplaceNoteRequest(ContractModel):
    request_id: str = Field(min_length=1, max_length=64)
    parent_place_name: str = Field(min_length=1, max_length=300)
    subplace_name: str = Field(min_length=1, max_length=300)
    offer_items: list[SubplaceOfferItemContext] = Field(min_length=1, max_length=20)


class GeneratedSubplaceNote(ContractModel):
    request_id: str = Field(min_length=1, max_length=64)
    note: str = Field(min_length=1, max_length=300)


class GeneratedSubplaceNoteBatch(ContractModel):
    notes: list[GeneratedSubplaceNote] = Field(default_factory=list)


class SubplaceSummary(ContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=300)
    address: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    image_url: str | None = Field(default=None, max_length=2048)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    cost_per_person: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=300)
    note_source: Literal["gemini"] | None = None
    note_activity_item_ids: list[str] = Field(default_factory=list, max_length=20)
    offer_items: list[SubplaceOfferItemContext] = Field(
        default_factory=list,
        max_length=20,
        exclude=True,
    )


class SubplaceGroup(ContractModel):
    parent_place_id: str = Field(min_length=1, max_length=300)
    total_count: int = Field(ge=0)
    items: list[SubplaceSummary] = Field(default_factory=list, max_length=50)
    parent_place_name: str | None = Field(default=None, max_length=300, exclude=True)
