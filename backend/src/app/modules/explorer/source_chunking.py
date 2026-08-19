import re
from urllib.parse import parse_qs, urlparse


def source_chunks(source, limit: int) -> list[list]:
    artifacts = []
    for artifact in source.artifacts:
        if len(artifact.text) <= limit:
            artifacts.append(artifact)
            continue
        paragraphs: list[str] = []
        for item in artifact.text.splitlines():
            paragraph = item.strip()
            if not paragraph:
                continue
            paragraphs.extend(
                paragraph[start : start + limit]
                for start in range(0, len(paragraph), limit)
            )
        current: list[str] = []
        size = 0
        for paragraph in paragraphs:
            if current and size + len(paragraph) > limit:
                artifacts.append(artifact.model_copy(update={"text": "\n".join(current)}))
                current, size = [], 0
            current.append(paragraph)
            size += len(paragraph)
        if current:
            artifacts.append(artifact.model_copy(update={"text": "\n".join(current)}))
    chunks: list[list] = []
    current = []
    size = 0
    for artifact in artifacts:
        if current and size + len(artifact.text) > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(artifact)
        size += len(artifact.text)
    if current:
        chunks.append(current)
    return prioritize_timestamp_chunk(chunks or [[]], source.source_ref)


def prioritize_timestamp_chunk(chunks: list[list], source_ref: str) -> list[list]:
    target = _url_timestamp_seconds(source_ref)
    if target is None:
        return chunks

    def distance(chunk: list) -> float:
        starts = [
            value
            for artifact in chunk
            if (value := _time_hint_seconds(artifact.source_time_hint)) is not None
        ]
        return min((abs(value - target) for value in starts), default=float("inf"))

    return sorted(chunks, key=distance)


def _url_timestamp_seconds(source_ref: str) -> int | None:
    values = parse_qs(urlparse(source_ref).query)
    raw = next(iter(values.get("t", values.get("start", []))), "").casefold()
    if raw.isdigit():
        return int(raw)
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", raw)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(value or 0) for value in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _time_hint_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        return None
    return hours * 3600 + minutes * 60 + seconds
