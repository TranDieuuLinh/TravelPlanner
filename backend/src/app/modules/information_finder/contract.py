from pydantic import BaseModel, Field


class InformationFinderInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class SourceReference(BaseModel):
    title: str
    url: str


class InformationFinderOutput(BaseModel):
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)

