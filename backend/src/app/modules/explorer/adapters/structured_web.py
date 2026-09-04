import re

from app.modules.explorer.contract import ExplorerPlace, PlaceSource
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult

_NUMBERED_H2 = re.compile(
    r"^\s*##(?!#)\s+(?:[*_\s]*)(?P<number>\d{1,3})\s*[.)]?\s*(?P<title>.+?)\s*$"
)
_MARKDOWN_LINK = re.compile(r"\[([^]]+)]\([^)]+\)")
_LEADING_ACTIVITY = re.compile(
    r"^(?:check[ -]?in|ghé thăm|tham quan)\s+",
    re.IGNORECASE,
)
_ACTIVITY_WITH_CONNECTOR = re.compile(
    r"^(?:ngắm|tìm hiểu|trải nghiệm|quay ngược)[^\n]{0,100}?\s+"
    r"(?:tại|ở|với)\s+(?P<place>.+)$",
    re.IGNORECASE,
)
_DESCRIPTIVE_SUFFIX = re.compile(
    r"\s+-\s+(?:biểu tượng|nơi|thiên đường|điểm|tọa độ|chốn)\b.+$",
    re.IGNORECASE,
)


def _plain_markdown(value: str) -> str:
    value = _MARKDOWN_LINK.sub(r"\1", value)
    value = re.sub(r"[*_`#]", "", value)
    return " ".join(value.strip(" -\t").split())


def _place_name(title: str) -> str:
    title = _plain_markdown(title)
    title = _DESCRIPTIVE_SUFFIX.sub("", title).strip()
    connected = _ACTIVITY_WITH_CONNECTOR.match(title)
    if connected:
        return connected.group("place").strip()
    return _LEADING_ACTIVITY.sub("", title).strip()


def places_from_numbered_web_headings(
    source: SourceExtractionResult,
) -> list[ExplorerPlace]:
    """Recover structurally explicit places when semantic synthesis is unavailable.

    Only numbered level-two headings are accepted. This intentionally excludes body
    prose and lower-level hotel/food lists, which are too ambiguous to promote to a
    TravelPlace without semantic validation.
    """
    places: list[ExplorerPlace] = []
    seen: set[str] = set()
    for artifact in source.artifacts:
        if artifact.artifact_type != "web_text":
            continue
        places.extend(_artifact_places(source, artifact, seen))
    return places


def _artifact_places(
    source: SourceExtractionResult,
    artifact: SourceArtifact,
    seen: set[str],
) -> list[ExplorerPlace]:
    places = []
    for line in artifact.text.splitlines():
        match = _NUMBERED_H2.match(line)
        if not match:
            continue
        name = _place_name(match.group("title"))
        key = name.casefold()
        if len(name) < 3 or len(name) > 200 or key in seen:
            continue
        seen.add(key)
        evidence = _plain_markdown(line)[:500]
        places.append(
            ExplorerPlace(
                name=name,
                confidence=0.72,
                sourcePlaces=[
                    PlaceSource(
                        origin="url",
                        evidenceType="web_text",
                        sourceUrl=artifact.source_url or source.source_ref,
                        evidence=evidence,
                        observedAt=artifact.observed_at,
                    )
                ],
            )
        )
    return places
