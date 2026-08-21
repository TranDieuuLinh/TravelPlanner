from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class LocalizationModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceNoteTranslationRequest(LocalizationModel):
    request_id: str = Field(min_length=1, max_length=64)
    place_name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)


class SourceNoteTranslation(LocalizationModel):
    request_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)


class SourceNoteTranslationBatch(LocalizationModel):
    translations: list[SourceNoteTranslation] = Field(default_factory=list)
