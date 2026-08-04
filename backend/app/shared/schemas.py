from pydantic import BaseModel, ConfigDict


class APIMessage(BaseModel):
    message: str


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
