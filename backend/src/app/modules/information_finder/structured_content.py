from __future__ import annotations

import re
import unicodedata

from app.modules.information_finder.normalization import normalize_generated_answer_text
from app.modules.information_finder.structured_blocks import (
    AnswerBlock,
    ComparisonBlock,
    FactItem,
    FactListBlock,
    NoticeBlock,
    ParagraphBlock,
    QuoteBlock,
    RecommendationsBlock,
    StepItem,
    StepsBlock,
    VerseBlock,
)


_SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_NOISE_MARKERS = (
    "previous",
    "next",
    "trang chủ",
    "lien ket website",
    "liên kết website",
    "site navigation",
    "skip to content",
    "bước tới nội dung",
    "tuyển dụng",
    "văn phòng",
    "chi nhánh",
    "breadcrumb",
    "menu",
    "footer",
    "header",
    "copyright",
    "discover flight",
    "@shutterstock",
    "bách khoa toàn thư mở",
    "bỏ qua nội dung",
    "truy cập nội dung từ url được cung cấp hiện không khả dụng",
    "hạn chế kỹ thuật",
    "tour du lịch hấp dẫn",
    "qua bài viết này",
)
_COMPANY_MARKER = re.compile(
    r"\b(?:công\s+ty|company|corporation|tnhh|cổ\s+phần|hotline|tổng\s+đài)\b",
    re.IGNORECASE,
)
_ENCODING_FRAGMENT = re.compile(r"(?:Ã.|Â.|â.{1,2}|�){2,}")


def clean_source_sentences(
    content: str,
    query: str,
    title: str = "",
    *,
    max_chars: int | None = None,
) -> list[str]:
    """Return short, useful source sentences without generic site chrome."""
    del query
    sentences: list[str] = []
    for raw in _SEGMENT_BOUNDARY.split(content.replace("\u00a0", " ")):
        sentence = re.sub(r"\s+", " ", raw).strip(" -•\t")
        if not sentence or _is_noise(sentence):
            continue
        if title and _same_as_source_title(sentence, title):
            continue
        if max_chars is not None and len(sentence) > max_chars:
            sentence = sentence[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
        if sentence and sentence not in sentences:
            sentences.append(sentence)
    return sentences


def normalize_answer_blocks(blocks: list[AnswerBlock]) -> list[AnswerBlock]:
    """Clean LLM blocks before citations, entity spans, or UI rendering."""
    normalized: list[AnswerBlock] = []
    for block in blocks:
        if isinstance(block, FactListBlock):
            items = [
                item.model_copy(
                    update={
                        "text": clean_text(item.text),
                        "inline_spans": [],
                    }
                )
                for item in block.items
                if clean_text(item.text)
            ][:5]
            if items:
                items = [
                    item.model_copy(update={"text": _limit_words(item.text, 25)})
                    for item in items
                ]
                normalized.append(block.model_copy(update={"items": items}))
            continue
        if isinstance(block, VerseBlock):
            lines = [clean_text(line) for line in block.lines]
            lines = [line for line in lines if line]
            if lines:
                normalized.append(
                    block.model_copy(update={"lines": lines, "inline_spans": []})
                )
            continue
        if isinstance(block, (RecommendationsBlock, StepsBlock, ComparisonBlock)):
            field = "options" if isinstance(block, ComparisonBlock) else "items"
            children = [
                child.model_copy(update={"inline_spans": []})
                for child in getattr(block, field)
                if _child_is_useful(child)
            ][:5]
            if children:
                normalized.append(block.model_copy(update={field: children}))
            continue
        if isinstance(block, (ParagraphBlock, QuoteBlock, NoticeBlock)):
            text = clean_text(block.text)
            if text:
                normalized.append(
                    block.model_copy(update={"text": text, "inline_spans": []})
                )
    return normalized


def clean_text(value: str) -> str:
    text = normalize_generated_answer_text(value)
    return "" if _is_noise(text) else text


def _child_is_useful(child) -> bool:
    if isinstance(child, FactItem):
        return bool(clean_text(child.text))
    if isinstance(child, StepItem):
        return bool(clean_text(child.text))
    if hasattr(child, "reason"):
        return bool(clean_text(child.reason)) and bool(clean_text(child.name))
    if hasattr(child, "pros"):
        return bool(clean_text(child.name))
    return False


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:")


def _is_noise(sentence: str) -> bool:
    folded = _fold(sentence)
    if _ENCODING_FRAGMENT.search(sentence):
        return True
    if any(_fold(marker) in folded for marker in _NOISE_MARKERS):
        return True
    return bool(_COMPANY_MARKER.search(sentence))


def _same_as_source_title(sentence: str, title: str) -> bool:
    """Drop provider snippets that contain only the page/video title."""
    return _fold(sentence).strip(" .") == _fold(title).strip(" .")


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
