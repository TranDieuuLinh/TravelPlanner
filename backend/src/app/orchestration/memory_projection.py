"""Small, deterministic adapters from conversation memory to agent inputs."""

from app.modules.explorer.public import ExplorerPlace, PlaceSource


SUPERVISOR_CONTEXT_LIMIT = 6


def supervisor_conversation_context(
    recent_messages: list[str] | None,
    previous_response: str | None,
) -> list[str]:
    """Keep a role-tagged, bounded transcript without repeating the current message."""
    context = list(recent_messages or [])
    tagged_response = f"Assistant: {previous_response}" if previous_response else None
    if tagged_response and tagged_response not in context:
        context.append(tagged_response)
    return context[-SUPERVISOR_CONTEXT_LIMIT:]


def memory_field(memory, name: str, default=None):
    if memory is None:
        return default
    value = getattr(memory, name, None)
    if value is not None:
        return value
    if isinstance(memory, dict):
        camel = name.split("_")[0] + "".join(
            part.capitalize() for part in name.split("_")[1:]
        )
        return memory.get(name, memory.get(camel, default))
    return default


def _active_facts(memory) -> list:
    facts = memory_field(memory, "active_facts", []) or []
    return [fact for fact in facts if memory_field(fact, "status") == "active"]


def _place_metadata(memory, name: str) -> tuple[str | None, str]:
    normalized = " ".join(name.casefold().split())
    for fact in _active_facts(memory):
        if memory_field(fact, "fact_type") != "place_candidate":
            continue
        value = memory_field(fact, "value")
        if not isinstance(value, str) or " ".join(value.casefold().split()) != normalized:
            continue
        provenance = memory_field(fact, "provenance")
        source_url = memory_field(provenance, "source_url")
        excerpt = memory_field(provenance, "source_excerpt") or f"Memory place: {name}"
        return source_url, str(excerpt)[:500]
    return None, f"Memory place: {name}"


def merge_memory_places(places, memory) -> list[ExplorerPlace]:
    """Keep Explorer evidence first and add unique, resolved memory candidates."""
    merged = [
        place if isinstance(place, ExplorerPlace) else ExplorerPlace.model_validate(place)
        for place in (places or [])
    ]
    known = {" ".join(place.name.casefold().split()) for place in merged}
    selected = memory_field(memory, "selected_places", []) or []
    mentioned = memory_field(memory, "mentioned_places", []) or []
    references = memory_field(memory, "active_references", []) or []
    resolved: list[str] = []
    for reference in references:
        entity = memory_field(reference, "resolved_entity")
        if not entity:
            continue
        resolved.extend(
            item.strip() for item in str(entity).split(",") if item.strip()
        )
    for name in [*selected, *mentioned, *resolved]:
        if not isinstance(name, str) or not name.strip():
            continue
        normalized = " ".join(name.casefold().split())
        if normalized in known:
            continue
        source_url, evidence = _place_metadata(memory, name)
        merged.append(
            ExplorerPlace(
                name=name,
                confidence=0.9 if source_url else 0.8,
                source_places=[
                    PlaceSource(
                        origin="url" if source_url else "input",
                        evidence_type="url_metadata" if source_url else "transcript",
                        source_url=source_url,
                        evidence=evidence,
                    )
                ],
            )
        )
        known.add(normalized)
    return merged


def information_query(state) -> str:
    """Add compact memory context, never the full transcript or raw payload."""
    message = (state.get("message") or "").strip()
    memory = state.get("conversation_memory")
    context: list[str] = []
    destination = memory_field(memory, "destination")
    if destination and destination.casefold() not in message.casefold():
        context.append(f"điểm đến: {destination}")
    references = state.get("resolved_references") or memory_field(
        memory, "active_references", []
    ) or []
    entities: list[str] = []
    for reference in references:
        entity = memory_field(reference, "resolved_entity")
        if entity and entity.casefold() not in {item.casefold() for item in entities}:
            entities.append(entity)
    if entities:
        context.append(f"địa điểm đang được nhắc tới: {', '.join(entities[:5])}")
    return message if not context else f"{message} (Ngữ cảnh chuyến đi: {'; '.join(context)})"

