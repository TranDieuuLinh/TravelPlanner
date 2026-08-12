from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LangfusePage(ObservabilityModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    page: int | None = None
    limit: int
    total: int | None = None
    has_more: bool | None = None


class LangfuseStatus(ObservabilityModel):
    configured: bool
    reachable: bool
    message: str
    project_count: int | None = None
