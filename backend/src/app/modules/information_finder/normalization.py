import re
import unicodedata


_NAVIGATION_MARKERS = (
    "turn your device in landscape mode",
    "current lang",
    "curent lang",
    "chọn điểm đến",
    "đăng nhập",
    "đăng ký",
    "bước tới nội dung",
    "skip to content",
    "site navigation",
    "theo dòng sự kiện",
)
_SEGMENT_BREAK = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_PROMOTIONAL_PHONE = re.compile(
    r"(?<!\d)(?:1900|0\d{2,3})(?:[\s().-]*\d){4,10}(?!\d)"
)
_PROMOTIONAL_LABEL = re.compile(
    r"\b(?:số\s+điện\s+thoại(?:\s+hỗ\s+trợ)?|phone|tổng\s+đài|hotline|"
    r"liên\s+hệ|đặt\s+tour|book\s+tour|tư\s+vấn)\b\s*:?-?",
    flags=re.IGNORECASE,
)
_PROMOTIONAL_BRAND = re.compile(
    r"\b(?:công\s+ty\s+(?:du\s+lịch|lữ\s+hành)|bestprice)\b",
    flags=re.IGNORECASE,
)
_PROMOTIONAL_LOCATION_LABEL = re.compile(
    r"\b(?:hà\s+nội|hồ\s+chí\s+minh|tp\.?\s*hcm)\s*:\s*",
    flags=re.IGNORECASE,
)


def normalize_answer_text(text: str) -> str:
    """Normalize extracted/generated text without changing its factual content."""
    normalized = _remove_promotional_fragments(text).replace("\u00a0", " ")
    normalized = re.sub(
        r"\[(?:sửa|edit)\s*\|\s*(?:sửa mã nguồn|edit source)\]",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"#{1,6}\s*", "", normalized)
    normalized = re.sub(r"\[\d+\]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_generated_answer_text(text: str) -> str:
    """Keep safe Markdown structure in an LLM-generated claim."""
    normalized = _remove_promotional_fragments(text).replace("\u00a0", " ")
    normalized = re.sub(
        r"\[([^\]]+)\]\(travel-entity://entity\)",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\[(?:sá»­a|edit)\s*\|\s*(?:sá»­a mÃ£ nguá»“n|edit source)\]",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\[\d+\]", "", normalized)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(lines).strip()


def select_relevant_excerpt(
    content: str,
    query: str,
    *,
    title: str = "",
    max_chars: int,
) -> str:
    """Select a query-relevant source excerpt instead of blindly using its prefix."""
    normalized = _normalize_for_selection(content)
    if len(normalized) <= max_chars:
        return normalize_answer_text(normalized)

    segments = _segments(normalized)
    query_terms = _tokens(query)
    title_terms = _tokens(title)
    scored = [
        (index, segment, _score_segment(segment, query_terms, title_terms))
        for index, segment in enumerate(segments)
        if segment
    ]
    if not scored:
        return normalize_answer_text(normalized[:max_chars].rstrip())

    content_scored = [
        item for item in scored if not _has_navigation_marker(item[1])
    ] or scored
    best_index, _, _ = max(content_scored, key=lambda item: item[2])
    selected = [segments[best_index]]
    total = len(selected[0])
    for distance in range(1, len(segments)):
        candidates = (
            best_index - distance,
            best_index + distance,
        )
        added = False
        for candidate_index in candidates:
            if not 0 <= candidate_index < len(segments):
                continue
            candidate = segments[candidate_index]
            if (
                not candidate
                or _has_navigation_marker(candidate)
                or total + len(candidate) + 1 > max_chars
            ):
                continue
            selected.append(candidate)
            total += len(candidate) + 1
            added = True
            break
        if not added and total >= max_chars:
            break

    excerpt = " ".join(selected)
    if len(excerpt) < max_chars:
        return normalize_answer_text(excerpt)
    return normalize_answer_text(excerpt[:max_chars].rsplit(" ", 1)[0].rstrip())


def _segments(text: str) -> list[str]:
    parts = _SEGMENT_BREAK.split(text)
    return [part.strip(" -•") for part in parts if part.strip(" -•")]


def _normalize_for_selection(text: str) -> str:
    normalized = _remove_promotional_fragments(text).replace("\u00a0", " ")
    normalized = re.sub(r"\[\d+\]", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n\s*", "\n", normalized)
    return normalized.strip()


def _remove_promotional_fragments(text: str) -> str:
    """Remove contact and advertising fragments from scraped travel content."""
    cleaned = _PROMOTIONAL_PHONE.sub(" ", text)
    cleaned = _PROMOTIONAL_LABEL.sub(" ", cleaned)
    cleaned = _PROMOTIONAL_BRAND.sub(" ", cleaned)
    cleaned = _PROMOTIONAL_LOCATION_LABEL.sub(" ", cleaned)
    return cleaned


def _score_segment(
    segment: str,
    query_terms: set[str],
    title_terms: set[str],
) -> float:
    folded = _fold(segment)
    segment_terms = _tokens(segment)
    query_overlap = len(segment_terms & query_terms)
    title_overlap = len(segment_terms & title_terms)
    marker_hits = sum(_fold(marker) in folded for marker in _NAVIGATION_MARKERS)
    short_label_penalty = 2.0 if len(segment_terms) < 8 else 0.0
    return (
        query_overlap * 10
        + title_overlap * 4
        + min(len(segment), 240) / 240
        - marker_hits * 12
        - short_label_penalty
    )


def _has_navigation_marker(segment: str) -> bool:
    folded = _fold(segment)
    return any(_fold(marker) in folded for marker in _NAVIGATION_MARKERS)


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[\wÀ-ỹ]+", _fold(text)) if len(token) > 1}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
