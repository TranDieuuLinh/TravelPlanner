from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class SourceNote(BaseModel):
    """Read-only note selected from URL or provider-backed place evidence."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    text: str = Field(min_length=1, max_length=4000)
    source_type: Literal["url", "google_maps", "knowledge_graph", "backend"]
    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_url", mode="before")
    @classmethod
    def keep_http_urls_only(cls, value: object) -> str | None:
        if value is None:
            return None
        url = str(value).strip()
        return url if url.casefold().startswith(("http://", "https://")) else None
