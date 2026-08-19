from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import VerificationStatus
from app.shared.contracts.source_note import SourceNote


def select_planner_source_note(checked: CheckedPlace) -> SourceNote | None:
    """Select one immutable source note, with URL evidence taking precedence."""

    url_note = next(
        (note for note in checked.provenance.url_notes if note.summary),
        None,
    )
    if url_note:
        return SourceNote(
            text=url_note.summary,
            source_type="url",
            source_url=url_note.source_url,
        )
    prefix = (
        "Cần xác minh đúng địa điểm/chi nhánh trước khi chốt lịch."
        if checked.verification.status == VerificationStatus.provisional
        else None
    )
    direct_url_source = next(
        (
            source
            for source in checked.provenance.source_places
            if source.origin.value == "url"
            and source.evidence
            and source.source_url
        ),
        None,
    )
    if direct_url_source:
        return SourceNote(
            text=(
                f"{prefix} {direct_url_source.evidence}"
                if prefix
                else direct_url_source.evidence
            ),
            source_type="url",
            source_url=direct_url_source.source_url,
        )
    if checked.provider_note:
        return checked.provider_note

    direct_source = next(
        (
            source
            for source in checked.provenance.source_places
            if source.origin.value != "system" and source.evidence
        ),
        None,
    )
    if direct_source:
        return SourceNote(
            text=(
                f"{prefix} {direct_source.evidence}"
                if prefix
                else direct_source.evidence
            ),
            source_type=(
                "url" if direct_source.origin.value == "url" else "backend"
            ),
            source_url=direct_source.source_url,
        )

    nearest = min(
        (
            relation
            for relation in checked.relationship_evidence
            if relation.relationship_type == "Special_Near"
            and relation.distance_km is not None
        ),
        key=lambda relation: relation.distance_km,
        default=None,
    )
    if nearest is None:
        return SourceNote(text=prefix, source_type="backend") if prefix else None
    note = (
        f"Cách {nearest.related_name or 'địa điểm liên quan'} "
        f"khoảng {nearest.distance_km:.2f} km theo Knowledge Graph."
    )
    return SourceNote(
        text=f"{prefix} {note}" if prefix else note,
        source_type="knowledge_graph",
        source_url=nearest.source,
    )
