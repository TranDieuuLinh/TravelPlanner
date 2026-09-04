from app.modules.explorer.contract import ExplorerPlace, PlaceSource
from app.modules.explorer.place_keys import place_name_key


def deduplicate_places(places: list[ExplorerPlace]) -> list[ExplorerPlace]:
    """Collapse exact normalized place names while preserving all source evidence."""
    result: list[ExplorerPlace] = []
    positions: dict[str, int] = {}
    for raw_place in places:
        place = (
            raw_place
            if isinstance(raw_place, ExplorerPlace)
            else ExplorerPlace.model_validate(raw_place)
        )
        key = place_name_key(place.name)
        if not key or key not in positions:
            positions[key] = len(result)
            result.append(place.model_copy(deep=True))
            continue
        index = positions[key]
        current = result[index]
        result[index] = current.model_copy(
            update={
                "address_hint": current.address_hint or place.address_hint,
                "confidence": max(current.confidence, place.confidence),
                "source_places": _merge_sources(
                    current.source_places, place.source_places
                ),
            }
        )
    return result


def _merge_sources(
    current: list[PlaceSource], incoming: list[PlaceSource]
) -> list[PlaceSource]:
    result = [source.model_copy(deep=True) for source in current]
    positions = {_source_key(source): index for index, source in enumerate(result)}
    for source in incoming:
        key = _source_key(source)
        if key not in positions:
            positions[key] = len(result)
            result.append(source.model_copy(deep=True))
            continue
        index = positions[key]
        stored = result[index]
        evidence = _merge_evidence(stored.evidence, source.evidence)
        result[index] = stored.model_copy(
            update={
                "evidence": evidence,
                "observed_at": source.observed_at or stored.observed_at,
            }
        )
    return result


def _source_key(source: PlaceSource) -> tuple:
    return (
        source.origin,
        source.evidence_type,
        (source.source_url or "").strip().casefold(),
        (source.source_time_hint or "").strip().casefold(),
        (source.address_hint or "").strip().casefold(),
    )


def _merge_evidence(first: str, second: str) -> str:
    values = list(
        dict.fromkeys(value.strip() for value in (first, second) if value.strip())
    )
    return "\n".join(values)[:500]
