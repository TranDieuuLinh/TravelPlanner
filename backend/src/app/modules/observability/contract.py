from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ObservabilityPage(ObservabilityModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    page: int | None = None
    limit: int
    total: int | None = None
    has_more: bool | None = None


class ObservabilityStatus(ObservabilityModel):
    configured: bool
    reachable: bool
    message: str
    trace_count: int = 0
    observation_count: int = 0
    error_count: int = 0
    retention_limit: int = 500
