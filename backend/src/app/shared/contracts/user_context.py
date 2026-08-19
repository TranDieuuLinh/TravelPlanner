from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class UserContextRequest(BaseModel):
    """A normalized request for user-owned context, not a user-facing question."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    field: str = Field(min_length=1, max_length=80)
    source_agent: str = Field(min_length=1, max_length=80)
    resume_route: str = Field(min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=240)
