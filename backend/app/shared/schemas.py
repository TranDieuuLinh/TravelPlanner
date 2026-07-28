from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIMessage(BaseModel):
    message: str


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class APIError(BaseModel):
    code: str
    message: str
    field_errors: dict[str, Any] = Field(default_factory=dict, alias="fieldErrors")
    request_id: str = Field(alias="requestId")

    model_config = ConfigDict(populate_by_name=True)
