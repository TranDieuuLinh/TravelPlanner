from typing import Annotated, Literal

from pydantic import Field

from app.modules.information_finder.contract import PublicModel


class TextSpan(PublicModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1)


class EntitySpan(PublicModel):
    type: Literal["entity"] = "entity"
    text: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)


InlineSpan = Annotated[TextSpan | EntitySpan, Field(discriminator="type")]


class ParagraphBlock(PublicModel):
    type: Literal["paragraph"] = "paragraph"
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class FactItem(PublicModel):
    label: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1)
    highlights: list[str] = Field(default_factory=list, max_length=3)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class FactListBlock(PublicModel):
    type: Literal["factList"] = "factList"
    title: str | None = Field(default=None, max_length=120)
    items: list[FactItem] = Field(min_length=1, max_length=5)


class VerseLine(PublicModel):
    text: str = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class VerseBlock(PublicModel):
    type: Literal["verse"] = "verse"
    title: str | None = Field(default=None, max_length=160)
    author: str | None = Field(default=None, max_length=120)
    lines: list[str] = Field(min_length=1, max_length=40)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class QuoteBlock(PublicModel):
    type: Literal["quote"] = "quote"
    text: str = Field(min_length=1)
    attribution: str | None = Field(default=None, max_length=160)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class RecommendationItem(PublicModel):
    name: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class RecommendationsBlock(PublicModel):
    type: Literal["recommendations"] = "recommendations"
    title: str | None = Field(default=None, max_length=120)
    items: list[RecommendationItem] = Field(min_length=1, max_length=5)


class StepItem(PublicModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class StepsBlock(PublicModel):
    type: Literal["steps"] = "steps"
    title: str | None = Field(default=None, max_length=120)
    items: list[StepItem] = Field(min_length=1, max_length=5)


class ComparisonOption(PublicModel):
    name: str = Field(min_length=1, max_length=160)
    pros: list[str] = Field(default_factory=list, max_length=5)
    cons: list[str] = Field(default_factory=list, max_length=5)
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


class ComparisonBlock(PublicModel):
    type: Literal["comparison"] = "comparison"
    title: str | None = Field(default=None, max_length=120)
    options: list[ComparisonOption] = Field(min_length=1, max_length=5)


class NoticeBlock(PublicModel):
    type: Literal["notice"] = "notice"
    text: str = Field(min_length=1)
    severity: Literal["info", "warning", "critical"] = "info"
    source_ids: list[str] = Field(min_length=1)
    inline_spans: list[InlineSpan] = Field(default_factory=list)


AnswerBlock = Annotated[
    ParagraphBlock
    | FactListBlock
    | VerseBlock
    | QuoteBlock
    | RecommendationsBlock
    | StepsBlock
    | ComparisonBlock
    | NoticeBlock,
    Field(discriminator="type"),
]
