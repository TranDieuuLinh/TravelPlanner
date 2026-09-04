from __future__ import annotations

from typing import Any


def expand_compact_place(raw_place: Any) -> tuple[Any, list[dict]]:
    if not isinstance(raw_place, dict) or "confidence" in raw_place:
        return raw_place, []
    allowed = {"name", "sourcePlaces", "source_places", "latitude", "longitude"}
    extras = set(raw_place) - allowed
    if extras:
        raise ValueError(f"unsupported compact place fields: {sorted(extras)}")
    sources = raw_place.get("sourcePlaces", raw_place.get("source_places", []))
    if not isinstance(sources, list):
        return raw_place, []
    expanded_sources = []
    notes = []
    for source in sources:
        expanded, source_notes = _expand_source(source, raw_place.get("name"))
        expanded_sources.append(expanded)
        notes.extend(source_notes)
    address_hint = next(
        (
            source.get("address_hint")
            for source in expanded_sources
            if isinstance(source, dict) and source.get("address_hint")
        ),
        None,
    )
    return {
        "name": raw_place.get("name"),
        "address_hint": address_hint,
        "confidence": 1,
        "source_places": expanded_sources,
        "latitude": raw_place.get("latitude"),
        "longitude": raw_place.get("longitude"),
        "tags": [],
    }, notes


def _expand_source(source: Any, place_name: str | None) -> tuple[Any, list[dict]]:
    if not isinstance(source, dict):
        return source, []
    allowed = {
        "evidenceType",
        "evidence_type",
        "sourceUrl",
        "source_url",
        "sourceTimeHint",
        "source_time_hint",
        "addressHint",
        "address_hint",
        "urlNotes",
        "url_notes",
    }
    extras = set(source) - allowed
    if extras:
        raise ValueError(f"unsupported compact source fields: {sorted(extras)}")
    evidence_type = source.get("evidenceType", source.get("evidence_type"))
    if evidence_type not in {"raw_prompt", "url"}:
        raise ValueError("evidenceType must be raw_prompt or url")
    source_url = source.get("sourceUrl", source.get("source_url"))
    if (evidence_type == "url") != bool(source_url):
        raise ValueError("sourceUrl must match evidenceType")
    raw_notes = source.get("urlNotes", source.get("url_notes", [])) or []
    summaries = [_note_summary(note) for note in raw_notes]
    notes = [
        {
            "summary": summary,
            "place_name": place_name,
            "evidence_type": evidence_type,
            "source_url": source_url,
        }
        for summary in summaries
    ]
    return {
        "origin": "url" if evidence_type == "url" else "input",
        "evidence_type": evidence_type,
        "source_url": source_url,
        "evidence": "\n".join(summaries) or place_name or evidence_type,
        "source_time_hint": source.get(
            "sourceTimeHint", source.get("source_time_hint")
        ),
        "address_hint": source.get("addressHint", source.get("address_hint")),
    }, notes


def _note_summary(note: Any) -> str:
    if not isinstance(note, dict) or set(note) != {"summary"}:
        raise ValueError("each compact urlNote must contain only summary")
    summary = note.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("urlNote summary must be a non-empty string")
    if len(summary) > 2000:
        raise ValueError("urlNote summary must not exceed 2000 characters")
    return summary.strip()


def expand_compact_item(item: Any) -> Any:
    if not isinstance(item, dict) or {"action", "evidence", "confidence"} & set(item):
        return item
    allowed = {
        "name",
        "itemType",
        "item_type",
        "relatedPlaceName",
        "related_place_name",
    }
    extras = set(item) - allowed
    if extras:
        raise ValueError(f"unsupported compact item fields: {sorted(extras)}")
    item_type = item.get("itemType", item.get("item_type"))
    action = {"food": "eat", "drink": "drink", "activity": "experience"}.get(
        str(item_type).casefold(), "experience"
    )
    return {
        "name": item.get("name"),
        "item_type": item_type,
        "related_place_name": item.get(
            "relatedPlaceName", item.get("related_place_name")
        ),
        "action": action,
        "evidence": item.get("name"),
        "confidence": 1,
    }


def expand_compact_budget(budget: dict) -> dict:
    if "source" in budget:
        return budget
    allowed = {
        "amountPerPerson",
        "amount_per_person",
        "targetAmount",
        "target_amount",
        "currency",
        "level",
    }
    extras = set(budget) - allowed
    if extras:
        raise ValueError(f"unsupported compact budget fields: {sorted(extras)}")
    amount = budget.get("targetAmount", budget.get("target_amount"))
    if amount is None:
        amount = budget.get("amountPerPerson", budget.get("amount_per_person"))
    return {
        "target_amount": amount,
        "currency": budget.get("currency", "VND"),
        "level": budget.get("level"),
        "source": "explorer",
        "basis": "per_person",
    }


def serialize_compact_handoff(payload) -> dict[str, Any]:
    return {
        "inputADM": payload.input_adm,
        "places": [_serialize_place(payload, place) for place in payload.places],
        "inputItems": [
            {
                "name": item.name,
                "itemType": item.item_type,
                "relatedPlaceName": item.related_place_name,
            }
            for item in payload.input_items
        ],
        "days": payload.days,
        "budget": {
            "amountPerPerson": (
                int(payload.budget.target_amount)
                if payload.budget.target_amount is not None
                else None
            ),
            "currency": payload.budget.currency or "VND",
            "level": payload.budget.level,
        },
        "people": payload.people.model_dump(by_alias=True),
        "shortPreferences": payload.short_preferences,
        "shortAvoids": payload.short_avoids,
        "specialNotes": payload.special_notes,
    }


def _serialize_place(payload, place) -> dict[str, Any]:
    return {
        "name": place.name,
        "sourcePlaces": [
            {
                "evidenceType": "url" if source.origin.value == "url" else "raw_prompt",
                "sourceUrl": source.source_url if source.origin.value == "url" else None,
                "sourceTimeHint": source.source_time_hint,
                "addressHint": source.address_hint or place.address_hint,
                "urlNotes": [
                    {"summary": note.summary}
                    for note in payload.url_notes
                    if note.place_name == place.name
                    and note.source_url == source.source_url
                ],
            }
            for source in place.source_places
        ],
        "latitude": place.latitude,
        "longitude": place.longitude,
    }
