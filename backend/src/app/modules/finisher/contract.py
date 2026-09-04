from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class FinisherModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FinisherNote(FinisherModel):
    place_name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=40)
    source_url: str | None = Field(default=None, max_length=2048)


class FinisherInput(FinisherModel):
    destination: str = Field(min_length=1, max_length=200)
    day_count: int = Field(ge=1, le=30)
    stop_count: int = Field(ge=1)
    notes: list[FinisherNote] = Field(default_factory=list, max_length=5)


class FinisherOutput(FinisherModel):
    response: str = Field(min_length=1, max_length=2000)
