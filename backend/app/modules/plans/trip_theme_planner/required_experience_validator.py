"""Pure validation of required experiences against graph evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from pydantic import ValidationError

from app.modules.knowledge_graph.research import (
    CheckStatus,
    EdgeEvidence,
    GraphEvidenceClaim,
    TripResearchBundle,
)
from app.modules.plans.dto.agent_contracts import (
    RequiredExperience,
    RequiredExperienceSelectionPolicy,
    TripThemeDraft,
)
from app.modules.plans.domain.entities import ExperienceCategory, PreferredTimeWindow
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    GraphCandidateCatalog,
    GraphExperienceCandidate,
    _activity_id,
    _place_ids,
)


class RequiredExperienceGraphValidationError(ValueError):
    """Raised when a requirement references unsupported graph evidence."""

    def __init__(self, message: str, *, code: str = "invalid_graph_output") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    reason: str
    path: str = ""


@dataclass(frozen=True)
class TripThemeValidationResult:
    """Repairable validation result for the TripThemePlanner boundary."""

    output: TripThemeDraft | None
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


_FORBIDDEN_OUTPUT_FIELDS = frozenset({
    "day", "route", "allocation", "scheduledDay", "scheduled_day",
    "dayIndex", "day_index", "routeId", "route_id", "allocationId",
    "allocation_id", "calendar", "calendarAllocation", "calendar_allocation",
})


def validate(
    output: TripThemeDraft | Mapping[str, Any],
    catalog: GraphCandidateCatalog,
) -> TripThemeValidationResult:
    """Validate and hydrate one complete TripThemePlanner output.

    This boundary is intentionally independent from Pydantic's schema errors so
    repair callers receive stable machine-readable reason codes.
    """
    errors: list[ValidationIssue] = []
    if isinstance(output, Mapping):
        leaked = _find_forbidden_fields(output)
        if leaked:
            return TripThemeValidationResult(
                output=None,
                errors=(ValidationIssue(
                    code="calendar_field_forbidden",
                    reason=f"Calendar field is not allowed in TripThemePlanner output: {leaked[0]}",
                    path=leaked[0],
                ),),
            )
        try:
            draft = TripThemeDraft.model_validate(output)
        except ValidationError as exc:
            first = exc.errors()[0]
            return TripThemeValidationResult(
                output=None,
                errors=(ValidationIssue(
                    code="schema_invalid",
                    reason=str(first.get("msg", "invalid TripThemeDraft")),
                    path=".".join(str(part) for part in first.get("loc", ())),
                ),),
            )
    else:
        draft = output

    if not catalog.candidates and draft.required_experiences:
        errors.append(ValidationIssue(
            code="catalog_empty",
            reason="requiredExperiences must be empty when graph catalog is empty.",
            path="requiredExperiences",
        ))

    claim_owner: dict[str, GraphExperienceCandidate] = {}
    for candidate in catalog.candidates:
        for claim_id in candidate.claim_ids:
            if claim_id in claim_owner:
                errors.append(ValidationIssue(
                    code="duplicate_catalog_claim",
                    reason=f"Claim ID appears in multiple catalog candidates: {claim_id}",
                    path="graphCandidateCatalog",
                ))
            claim_owner[claim_id] = candidate

    used_claims: set[str] = set()
    hydrated: list[RequiredExperience] = []
    warnings: list[ValidationIssue] = []
    for index, requirement in enumerate(draft.required_experiences):
        path = f"requiredExperiences[{index}]"
        candidate, issue = _candidate_for_requirement(requirement, catalog)
        if issue is not None:
            errors.append(ValidationIssue(issue[0], issue[1], path))
            continue
        assert candidate is not None
        if not candidate.is_special_experience:
            errors.append(ValidationIssue(
                code="not_special_experience",
                reason=(
                    "TripThemePlanner may only select candidates backed by "
                    "SPECIAL_EXPERIENCE."
                ),
                path=path,
            ))
            continue
        if not set(requirement.claim_ids).intersection(candidate.special_claim_ids):
            errors.append(ValidationIssue(
                code="special_claim_required",
                reason=(
                    "Each highlight must cite at least one SPECIAL_EXPERIENCE "
                    "claim from its catalog candidate."
                ),
                path=f"{path}.claimIds",
            ))
            continue

        duplicate_claims = used_claims.intersection(requirement.claim_ids)
        if duplicate_claims:
            errors.append(ValidationIssue(
                code="duplicate_claim",
                reason=f"Claim is selected more than once: {sorted(duplicate_claims)[0]}",
                path=f"{path}.claimIds",
            ))
        used_claims.update(requirement.claim_ids)

        if requirement.category != candidate.category:
            errors.append(ValidationIssue(
                code="classification_mismatch",
                reason=(f"category must match catalog candidate category "
                        f"'{candidate.category.value}'."),
                path=f"{path}.category",
            ))
        if requirement.category in {ExperienceCategory.meal, ExperienceCategory.food}:
            # Meal/food candidates remain meal inputs and cannot be promoted to
            # a main experience by the model.
            if requirement.theme.casefold() in {"main", "main experience"}:
                errors.append(ValidationIssue(
                    code="meal_classification_invalid",
                    reason="Meal/food candidates cannot be classified as main experience.",
                    path=f"{path}.theme",
                ))
        hydrated.append(_hydrate_timing(requirement, candidate))

    if errors:
        return TripThemeValidationResult(output=None, errors=tuple(errors), warnings=tuple(warnings))
    return TripThemeValidationResult(
        output=draft.model_copy(update={"required_experiences": hydrated}),
        warnings=tuple(warnings),
    )


def _find_forbidden_fields(value: Any, path: str = "") -> list[str]:
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, child in value.items():
            key_path = f"{path}.{key}" if path else str(key)
            if key in _FORBIDDEN_OUTPUT_FIELDS:
                found.append(key_path)
            found.extend(_find_forbidden_fields(child, key_path))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(_find_forbidden_fields(child, f"{path}[{index}]"))
        return found
    return []


def _candidate_for_requirement(
    requirement: RequiredExperience,
    catalog: GraphCandidateCatalog,
) -> tuple[GraphExperienceCandidate | None, tuple[str, str] | None]:
    claim_ids = set(requirement.claim_ids)
    graph_claim_ids = {claim for candidate in catalog.candidates for claim in candidate.claim_ids}
    graph_place_ids = {
        place_id
        for candidate in catalog.candidates
        for place_id in (candidate.place_ids + candidate.anchor_place_ids + candidate.candidate_place_ids)
    }
    graph_activity_ids = {
        candidate.activity_id for candidate in catalog.candidates if candidate.activity_id
    }
    for value in sorted(claim_ids - graph_claim_ids):
        return None, ("unknown_graph_id", f"Unknown graph claim ID: {value}.")
    for value in sorted(
        (set(requirement.anchor_place_ids) | set(requirement.candidate_place_ids)) - graph_place_ids
    ):
        return None, ("unknown_graph_id", f"Unknown graph place ID: {value}.")
    if requirement.activity_id and requirement.activity_id not in graph_activity_ids:
        return None, ("unknown_graph_id", f"Unknown graph activity ID: {requirement.activity_id}.")

    if requirement.selection_policy is RequiredExperienceSelectionPolicy.required_anchor:
        required_ids = set(requirement.anchor_place_ids)
        candidates = [c for c in catalog.candidates if required_ids.issubset(set(c.anchor_place_ids))]
    elif requirement.selection_policy is RequiredExperienceSelectionPolicy.choose_one:
        required_ids = set(requirement.candidate_place_ids)
        candidates = [c for c in catalog.candidates if required_ids.issubset(set(c.candidate_place_ids or c.place_ids))]
    else:
        candidates = [c for c in catalog.candidates if c.activity_id == requirement.activity_id]

    candidates = [c for c in candidates if claim_ids.issubset(set(c.claim_ids))]
    identifier_candidates = candidates
    candidates = [c for c in candidates if set(requirement.source_refs).issubset(set(c.source_refs))]
    if not candidates:
        if identifier_candidates and requirement.source_refs:
            return None, ("provenance_mismatch", "claimIds and sourceRefs do not belong to one catalog candidate.")
        return None, ("selection_policy_invalid", "Selected graph IDs do not satisfy one catalog candidate and selection policy.")

    candidate = candidates[0]
    if requirement.selection_policy is RequiredExperienceSelectionPolicy.choose_one:
        count = len(set(candidate.candidate_place_ids or candidate.place_ids))
        if requirement.minimum_required > count:
            return None, ("minimum_required_exceeds_candidates", "minimumRequired exceeds candidate places in the selected graph candidate.")
    return candidate, None


def _hydrate_timing(requirement: RequiredExperience, candidate: GraphExperienceCandidate) -> RequiredExperience:
    recommendation = candidate.recommendation
    windows = _normalize_preferred_time_windows(recommendation.timeSlots) if recommendation else []
    duration = (
        recommendation.recommendedVisitMinutes
        if recommendation and recommendation.recommendedVisitMinutes is not None
        and 15 <= recommendation.recommendedVisitMinutes <= 720
        else None
    )
    return requirement.model_copy(update={
        "preferred_time_windows": windows,
        "recommended_visit_minutes": duration,
    })


def _theme_candidate_count(theme: Any, catalog: GraphCandidateCatalog) -> int:
    # Theme focus tags are narrative guidance, not graph IDs. The bounded
    # catalog is therefore the only deterministic count available at this
    # stage; category/route fitting belongs to PlaceSelector.
    return len(catalog.candidates)


def validate_required_experience(
    requirement: RequiredExperience,
    evidence: TripResearchBundle | GraphCandidateCatalog,
) -> RequiredExperience:
    """Validate one requirement against a bounded research graph/catalog."""
    claims = _claims(evidence)
    claim_by_id = {claim.claimId: claim for claim in claims}
    if len(claim_by_id) != len(claims):
        raise RequiredExperienceGraphValidationError("duplicate claim IDs in evidence")

    selected_claims = []
    for claim_id in requirement.evidence_claim_ids:
        claim = claim_by_id.get(claim_id)
        if claim is None:
            raise RequiredExperienceGraphValidationError(
                f"unknown evidence claim ID: {claim_id}"
            )
        selected_claims.append(claim)

    if len(set(requirement.evidence_claim_ids)) != len(requirement.evidence_claim_ids):
        raise RequiredExperienceGraphValidationError("duplicate evidence claim IDs")
    evidence_sources = {
        source
        for claim in selected_claims
        for item in claim.evidence
        if (source := item.source)
    }
    missing_sources = set(requirement.source_refs) - evidence_sources
    if missing_sources:
        raise RequiredExperienceGraphValidationError(
            f"sourceRefs not present in evidence: {sorted(missing_sources)}"
        )

    place_ids = {place_id for claim in selected_claims for place_id in _place_ids(claim)}
    activities = {_activity_id(claim) for claim in selected_claims} - {None}
    policy = requirement.selection_policy
    if policy is RequiredExperienceSelectionPolicy.required_anchor:
        if not set(requirement.anchor_place_ids) <= place_ids:
            raise RequiredExperienceGraphValidationError("anchor place is not evidence-backed")
    elif policy is RequiredExperienceSelectionPolicy.choose_one:
        if not set(requirement.candidate_place_ids) <= place_ids:
            raise RequiredExperienceGraphValidationError("candidate place is not evidence-backed")
        if len(activities) != 1:
            raise RequiredExperienceGraphValidationError("choose_one candidates must share one activity")
    elif policy is RequiredExperienceSelectionPolicy.open_candidate:
        if requirement.activity_id not in activities:
            raise RequiredExperienceGraphValidationError("open candidate activity is not evidence-backed")
    if isinstance(evidence, GraphCandidateCatalog):
        return _enrich_timing_guidance(requirement, evidence)
    return requirement


_CLOCK_RANGE = re.compile(
    r"^\s*((?:[01]?\d|2[0-3]):[0-5]\d)\s*-\s*"
    r"((?:[01]?\d|2[0-3]):[0-5]\d)\s*$"
)
_DAY_PART_WINDOWS = {
    "morning": ("09:00", "12:00"),
    "afternoon": ("13:00", "18:00"),
    "evening": ("19:00", "21:00"),
    "night": ("19:00", "21:00"),
}


def _enrich_timing_guidance(
    requirement: RequiredExperience,
    catalog: GraphCandidateCatalog,
) -> RequiredExperience:
    """Hydrate graph timing server-side instead of trusting LLM-echoed values."""

    claim_ids = set(requirement.evidence_claim_ids)
    candidates = [
        candidate
        for candidate in catalog.candidates
        if claim_ids and claim_ids <= set(candidate.claim_ids)
    ]
    recommendation = (
        candidates[0].recommendation if len(candidates) == 1 else None
    )
    windows = (
        _normalize_preferred_time_windows(recommendation.timeSlots)
        if recommendation is not None
        else []
    )
    duration = (
        recommendation.recommendedVisitMinutes
        if recommendation is not None
        and recommendation.recommendedVisitMinutes is not None
        and 15 <= recommendation.recommendedVisitMinutes <= 720
        else None
    )
    return requirement.model_copy(
        update={
            "preferred_time_windows": windows,
            "recommended_visit_minutes": duration,
        }
    )


def _normalize_preferred_time_windows(
    raw_slots: Iterable[str | dict],
) -> list[PreferredTimeWindow]:
    windows: list[PreferredTimeWindow] = []
    seen: set[tuple[str, str]] = set()
    for raw_slot in raw_slots:
        start: str | None = None
        end: str | None = None
        if isinstance(raw_slot, dict):
            raw_start = raw_slot.get("start")
            raw_end = raw_slot.get("end")
            if isinstance(raw_start, str) and isinstance(raw_end, str):
                start, end = raw_start, raw_end
        elif isinstance(raw_slot, str):
            match = _CLOCK_RANGE.fullmatch(raw_slot)
            if match is not None:
                start, end = match.groups()
            else:
                start, end = _DAY_PART_WINDOWS.get(
                    raw_slot.strip().casefold().replace("_", " "),
                    (None, None),
                )
        if start is None or end is None:
            continue
        start = _canonical_clock(start)
        end = _canonical_clock(end)
        key = (start, end)
        if key in seen:
            continue
        try:
            window = PreferredTimeWindow(start=start, end=end)
        except ValueError:
            continue
        seen.add(key)
        windows.append(window)
    return windows


def _canonical_clock(value: str) -> str:
    hour, minute = value.strip().split(":", 1)
    return f"{int(hour):02d}:{int(minute):02d}"


def _claims(evidence: TripResearchBundle | GraphCandidateCatalog) -> list[GraphEvidenceClaim]:
    if isinstance(evidence, TripResearchBundle):
        conflicted = {item.claim.claimId for item in evidence.conflictedExperiences}
        unknown = {item.claimId for item in evidence.unknowns}
        if conflicted or unknown:
            raise RequiredExperienceGraphValidationError("conflicted or unknown claims are not eligible")
        return [item.claim for item in evidence.eligibleExperiences if item.fit.status is CheckStatus.SUPPORTED and not item.fit.hasHardConflict]
    return _synthetic_claims_from_catalog(evidence)


def _synthetic_claims_from_catalog(
    catalog: GraphCandidateCatalog,
) -> list[GraphEvidenceClaim]:
    """Build synthetic ``GraphEvidenceClaim`` rows from a bounded catalog.

    The catalog only carries the IDs that survived the projection step. We
    rebuild minimal claim entities with the activity/anchor/source fields that
    the validator helpers need, while keeping the validation graph-bounded.

    Each catalog ``claim_id`` corresponds to one anchor Place in the source
    ranking. We emit one synthetic claim per ``claim_id`` that exposes its
    corresponding anchor. When the catalog only has anchor Places (no claim
    IDs), the first anchor itself becomes the claim identifier so that
    validators still receive a populated ``anchorPlace.id``.
    """

    claims: list[GraphEvidenceClaim] = []
    for candidate in catalog.candidates:
        candidate_evidence = [
            EdgeEvidence(source=source, recommendations=[])
            for source in candidate.source_refs
            if source
        ]
        anchors: list[str | None] = (
            list(candidate.anchor_place_ids)
            or list(candidate.place_ids)
            or [None]
        )
        activity_id = candidate.activity_id
        activity_entity = (
            _synthetic_entity(activity_id, "Activity") if activity_id else None
        )
        claim_ids = list(candidate.claim_ids)
        if not claim_ids:
            claim_ids = [anchor for anchor in anchors if anchor is not None]
        for index, claim_id in enumerate(claim_ids):
            anchor_id = anchors[min(index, len(anchors) - 1)]
            subject = _synthetic_entity(
                anchor_id or "graph-scope",
                "TravelPlace" if anchor_id else "Area",
            )
            object_entity = (
                activity_entity
                if activity_entity is not None
                else _synthetic_entity(anchor_id or "graph-scope", "Area")
            )
            predicate = (
                "OFFERS_ACTIVITY"
                if activity_id is not None and anchor_id is not None
                else "SPECIAL_EXPERIENCE"
            )
            claims.append(
                GraphEvidenceClaim.model_construct(
                    claimId=claim_id,
                    subject=subject,
                    predicate=predicate,
                    object=object_entity,
                    path=[],
                    anchorPlace=subject if anchor_id is not None else None,
                    activity=activity_entity,
                    recommendations=[],
                    evidence=candidate_evidence,
                    trust="SOURCE_BACKED",
                    inferenceSource=None,
                    warnings=[],
                )
            )
    return claims


def _synthetic_entity(entity_id: str | None, entity_type: str) -> object:
    return _EntitySummaryStub(id=entity_id, name=entity_id or "", type=entity_type, status="verified")


class _EntitySummaryStub:
    """Minimal duck-typed entity matching the validator's expectations."""

    __slots__ = ("id", "name", "type", "status")

    def __init__(self, *, id: str, name: str, type: str, status: str) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.status = status


validate_required_experiences = validate_required_experience
