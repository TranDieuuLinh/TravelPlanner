from __future__ import annotations

from typing import Any

from app.modules.knowledge_graph.research import CheckStatus, FitResult, Recommendation, RecommendationPriority, TrustLevel
from app.modules.plans.domain.entities import ExperienceCategory
from app.modules.plans.trip_theme_planner.graph_candidate_projection import GraphCandidateCatalog, GraphExperienceCandidate
from app.modules.plans.trip_theme_planner.required_experience_validator import validate


def _candidate(
    *,
    claim: str = "claim-a",
    place: str = "place-a",
    source: str = "source-a",
    activity: str = "activity-a",
    category: ExperienceCategory = ExperienceCategory.main_experience,
) -> GraphExperienceCandidate:
    return GraphExperienceCandidate(
        claimIds=[claim],
        specialClaimIds=[claim],
        placeIds=[place],
        candidatePlaceIds=[place],
        activityId=activity,
        activityName="Coffee tour",
        category=category,
        anchorPlaceIds=[place],
        isSpecialExperience=True,
        rank=1,
        fit=FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1),
        trust=TrustLevel.SOURCE_BACKED,
        recommendation=Recommendation(
            priority=RecommendationPriority.RECOMMENDED,
            timeSlots=["morning"],
            recommendedVisitMinutes=90,
        ),
        sourceRefs=[source],
    )


def _requirement(**overrides: Any) -> dict[str, Any]:
    value = {
        "requirementId": "req-a",
        "theme": "coffee",
        "category": "main_experience",
        "activityId": "activity-a",
        "selectionPolicy": "required_anchor",
        "anchorPlaceIds": ["place-a"],
        "candidatePlaceIds": [],
        "minimumRequired": 1,
        "reason": "A graph-backed experience",
        "claimIds": ["claim-a"],
        "evidenceClaimIds": ["claim-a"],
        "sourceRefs": ["source-a"],
        "preferredTimeWindows": [{"start": "22:00", "end": "23:00"}],
        "recommendedVisitMinutes": 720,
    }
    value.update(overrides)
    return value


def _catalog(*candidates: GraphExperienceCandidate) -> GraphCandidateCatalog:
    return GraphCandidateCatalog(candidates=list(candidates))


def test_unknown_id_is_rejected_with_repair_code() -> None:
    result = validate({"requiredExperiences": [_requirement(claimIds=["missing"], evidenceClaimIds=["missing"])]}, _catalog(_candidate()))

    assert result.is_valid is False
    assert result.errors[0].code == "unknown_graph_id"


def test_calendar_fields_are_rejected_before_schema_parsing() -> None:
    result = validate({"requiredExperiences": [_requirement(day=2)]}, _catalog(_candidate()))

    assert result.errors[0].code == "calendar_field_forbidden"


def test_duplicate_claim_and_mixed_source_are_rejected() -> None:
    first = _candidate()
    second = _candidate(claim="claim-b", place="place-b", source="source-b", activity="activity-b")
    duplicate = validate(
        {"requiredExperiences": [_requirement(), _requirement(requirementId="req-b")]},
        _catalog(first),
    )
    mixed = validate(
        {"requiredExperiences": [_requirement(claimIds=["claim-a"], evidenceClaimIds=["claim-a"], sourceRefs=["source-b"])]},
        _catalog(first, second),
    )

    assert duplicate.errors[0].code == "duplicate_claim"
    assert mixed.errors[0].code == "provenance_mismatch"


def test_selection_policy_and_classification_are_validated_without_theme_quota() -> None:
    policy = validate(
        {"requiredExperiences": [_requirement(claimIds=["claim-b"], evidenceClaimIds=["claim-b"])]},
        _catalog(_candidate(), _candidate(claim="claim-b", place="place-b", source="source-b", activity="activity-b")),
    )
    classification = validate(
        {"requiredExperiences": [_requirement(category="meal")]},
        _catalog(_candidate()),
    )
    minimum = validate(
        {
            "tripThemes": [{"theme": "coffee", "minimumActivities": 2}],
            "requiredExperiences": [],
        },
        _catalog(_candidate()),
    )

    assert policy.errors[0].code == "selection_policy_invalid"
    assert classification.errors[0].code == "classification_mismatch"
    assert minimum.is_valid is True


def test_valid_output_hydrates_catalog_timing_and_ignores_llm_timing() -> None:
    result = validate({"requiredExperiences": [_requirement()]}, _catalog(_candidate()))

    assert result.is_valid is True
    assert result.output is not None
    hydrated = result.output.required_experiences[0]
    assert hydrated.recommended_visit_minutes == 90
    assert hydrated.preferred_time_windows[0].start == "09:00"
    assert hydrated.preferred_time_windows[0].end == "12:00"


def test_highlight_must_cite_its_special_experience_claim() -> None:
    candidate = _candidate().model_copy(
        update={
            "claim_ids": ["claim-special", "claim-offer"],
            "special_claim_ids": ["claim-special"],
        }
    )
    result = validate(
        {
            "requiredExperiences": [
                _requirement(
                    claimIds=["claim-offer"],
                    evidenceClaimIds=["claim-offer"],
                )
            ]
        },
        _catalog(candidate),
    )

    assert result.is_valid is False
    assert result.errors[0].code == "special_claim_required"


def test_empty_catalog_accepts_empty_output_and_rejects_requirements() -> None:
    valid = validate({"requiredExperiences": []}, GraphCandidateCatalog())
    invalid = validate({"requiredExperiences": [_requirement()]}, GraphCandidateCatalog())

    assert valid.is_valid is True
    assert invalid.errors[0].code == "catalog_empty"
