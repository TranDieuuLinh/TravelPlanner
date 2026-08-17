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


def _find_matching_place_fact(memory, name: str):
    normalized = " ".join(name.casefold().split())
    for fact in _active_facts(memory):
        if memory_field(fact, "fact_type") != "place_candidate":
            continue
        value = memory_field(fact, "value")
        if isinstance(value, str) and " ".join(value.casefold().split()) == normalized:
            return fact
    return None


def _place_metadata(memory, name: str) -> tuple[str | None, str]:
    fact = _find_matching_place_fact(memory, name)
    if fact is not None:
        provenance = memory_field(fact, "provenance")
        source_url = memory_field(provenance, "source_url")
        excerpt = memory_field(provenance, "source_excerpt") or f"Memory place: {name}"
        return source_url, str(excerpt)[:500]
    return None, f"Memory place: {name}"


def _resolve_place_provenance(
    memory,
    name: str,
    *,
    is_selected: bool,
    is_resolved: bool,
) -> tuple[str, str, str | None, float, str]:
    """Resolve origin, evidence_type, source_url, confidence, and evidence for a place.

    Returns:
        tuple[origin, evidence_type, source_url, confidence, evidence]
    """
    matching_fact = _find_matching_place_fact(memory, name)
    source_url = None
    evidence = f"Memory place: {name}"
    extracted_by = ""
    source_message_id = ""
    confirmed_by_user = False
    fact_confidence = 0.8

    if matching_fact is not None:
        provenance = memory_field(matching_fact, "provenance")
        source_url = memory_field(provenance, "source_url")
        raw_excerpt = memory_field(provenance, "source_excerpt")
        if raw_excerpt:
            evidence = str(raw_excerpt)[:500]
        extracted_by = str(memory_field(provenance, "extracted_by") or "")
        source_message_id = str(memory_field(provenance, "source_message_id") or "")
        confirmed_by_user = bool(memory_field(matching_fact, "confirmed_by_user"))
        fact_confidence = float(memory_field(provenance, "confidence") or 0.8)

    # 1. Detect if fact is assistant-generated
    is_assistant = (
        matching_fact is not None
        and (
            extracted_by.startswith("information_finder")
            or source_message_id.startswith("assistant:")
            or extracted_by == "bootstrap"
            or (not confirmed_by_user and "assistant" in extracted_by)
        )
    )

    # 2. Explicit current-turn reference promotion takes precedence
    if is_resolved:
        return "input", "transcript", None, 0.85, f"User referenced place: {name}"

    # 3. Direct user selection or user confirmation
    if is_selected or confirmed_by_user:
        if source_url and not is_assistant:
            return "url", "url_metadata", source_url, 0.9, evidence
        return "input", "transcript", None, 0.85, evidence

    # 4. Assistant-derived unconfirmed facts (including assistant citation URLs) must remain system/optional
    if is_assistant:
        return "system", "transcript", None, min(fact_confidence, 0.7), evidence

    # 5. User-derived URL facts
    if source_url:
        return "url", "url_metadata", source_url, 0.9, evidence

    # 6. User prompt facts
    if matching_fact is not None:
        if source_message_id.startswith("user:") or extracted_by.startswith("rule_based"):
            return "input", "transcript", None, min(fact_confidence, 0.8), evidence
        return "system", "transcript", None, min(fact_confidence, 0.7), evidence

    # 7. Legacy/stale mentioned places without fact metadata
    return "system", "transcript", None, 0.7, evidence


def merge_memory_places(
    places,
    memory,
    *,
    resolved_references: list | None = None,
) -> list[ExplorerPlace]:
    """Keep Explorer evidence first and add unique memory candidates with provenance.

    Only current-turn resolved_references promote suggestions to user inputs.
    """
    merged = [
        place if isinstance(place, ExplorerPlace) else ExplorerPlace.model_validate(place)
        for place in (places or [])
    ]
    known = {" ".join(place.name.casefold().split()) for place in merged}
    selected_raw = memory_field(memory, "selected_places", []) or []
    selected_set = {
        " ".join(str(s).casefold().split()) for s in selected_raw if str(s).strip()
    }
    mentioned = memory_field(memory, "mentioned_places", []) or []
    resolved: list[str] = []
    for reference in (resolved_references or []):
        entity = memory_field(reference, "resolved_entity")
        if not entity:
            continue
        resolved.extend(
            item.strip() for item in str(entity).split(",") if item.strip()
        )
    resolved_set = {
        " ".join(str(r).casefold().split()) for r in resolved if str(r).strip()
    }

    for name in [*selected_raw, *resolved, *mentioned]:
        if not isinstance(name, str) or not name.strip():
            continue
        normalized = " ".join(name.casefold().split())
        if normalized in known:
            continue
        is_selected = normalized in selected_set
        is_resolved = normalized in resolved_set
        origin, evidence_type, source_url, confidence, evidence = _resolve_place_provenance(
            memory,
            name,
            is_selected=is_selected,
            is_resolved=is_resolved,
        )
        merged.append(
            ExplorerPlace(
                name=name,
                confidence=confidence,
                source_places=[
                    PlaceSource(
                        origin=origin,
                        evidence_type=evidence_type,
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


def build_blocked_clarification(output) -> tuple[str, str]:
    dest = getattr(output.trip_context, "destination", None)
    dest_status = getattr(dest, "status", None)
    dest_status_val = (
        getattr(dest_status, "value", str(dest_status)) if dest_status else None
    )
    dest_name = getattr(dest, "input_name", "điểm đến") if dest else "điểm đến"

    if dest_status_val and dest_status_val != "resolved":
        return (
            f"Không thể xác định rõ điểm đến '{dest_name}'. Bạn có thể cung cấp tên tỉnh hoặc thành phố cụ thể hơn không?",
            f"Điểm đến '{dest_name}' chưa được xác định rõ.",
        )

    blocked_mandatory = [
        p
        for p in getattr(output, "checked_places", [])
        if getattr(p, "mandatory", False)
        and getattr(getattr(p, "evaluation", None), "state", None)
        in {
            "blocked",
            getattr(
                getattr(getattr(p, "evaluation", None), "state", None), "value", None
            ),
        }
    ]
    if blocked_mandatory:
        names = [
            getattr(p, "canonical_name", None)
            or (
                getattr(p, "original_names", [None])[0]
                if getattr(p, "original_names", None)
                else "địa điểm"
            )
            for p in blocked_mandatory
        ]
        names_str = ", ".join(dict.fromkeys(names))
        return (
            f"Địa điểm bắt buộc '{names_str}' chưa được xác minh hoặc không phù hợp với chuyến đi. Bạn có thể bổ sung tên hoặc địa chỉ chính xác hơn không?",
            f"Địa điểm bắt buộc '{names_str}' cần làm rõ dữ liệu trước khi lập lịch.",
        )

    unresolved_mandatory = [
        u
        for u in getattr(output, "unresolved_entities", [])
        if getattr(u, "mandatory", False)
    ]
    if unresolved_mandatory:
        names = [
            getattr(u, "input_name", None) or "thông tin" for u in unresolved_mandatory
        ]
        names_str = ", ".join(dict.fromkeys(names))
        return (
            f"Thông tin bắt buộc '{names_str}' chưa được làm rõ. Bạn có thể bổ sung thêm chi tiết không?",
            f"Thông tin '{names_str}' cần làm rõ trước khi lập lịch.",
        )

    warnings = getattr(output, "warnings", [])
    reason_msg = (
        warnings[0] if warnings else "Dữ liệu địa điểm chưa đủ điều kiện lập lịch."
    )
    return (
        f"{reason_msg} Bạn có thể điều chỉnh yêu cầu hoặc bổ sung thông tin không?",
        f"PlaceChecker không thể lập lịch: {reason_msg}",
    )

