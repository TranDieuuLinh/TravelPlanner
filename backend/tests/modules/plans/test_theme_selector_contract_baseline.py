from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.plans.domain.entities import ExperienceCategory
from app.modules.plans.dto.agent_contracts import RequiredExperience
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    build_candidate_contract,
)


def _fixture(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "activityId": "activity_hanoi_walk",
        "claimIds": ["claim_hanoi_walk"],
        "anchorPlaceIds": ["place_hoan_kiem"],
        "candidatePlaceIds": [],
        "category": "main_experience",
        "recommendation": {
            "priority": "must",
            "timeSlots": ["morning"],
        },
        "nodeProperties": {"timeSlots": ["evening"]},
    }
    payload.update(overrides)
    return payload


def test_candidate_contract_exposes_ids_provenance_category_and_edge_timing() -> None:
    result = build_candidate_contract(_fixture())

    assert result["activityId"] == "activity_hanoi_walk"
    assert result["claimIds"] == ["claim_hanoi_walk"]
    assert result["anchorPlaceIds"] == ["place_hoan_kiem"]
    assert result["category"] == "main_experience"
    assert result["recommendation"]["timeSlots"] == ["morning"]
    assert "day" not in result


def test_candidate_contract_uses_node_timing_when_edge_has_none() -> None:
    result = build_candidate_contract(
        _fixture(recommendation={"priority": "recommended"})
    )

    assert result["recommendation"]["timeSlots"] == ["evening"]


def test_candidate_contract_rejects_duplicate_claim_ids() -> None:
    with pytest.raises(ValidationError, match="claimIds"):
        build_candidate_contract(_fixture(claimIds=["claim-1", "claim-1"]))


def test_candidate_contract_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError, match="category"):
        build_candidate_contract(_fixture(category="breakfast"))


def test_required_experience_accepts_canonical_claim_ids_and_meal_category() -> None:
    requirement = RequiredExperience.model_validate(
        {
            "requirementId": "req-meal",
            "theme": "Bun cha",
            "category": "meal",
            "selectionPolicy": "required_anchor",
            "anchorPlaceIds": ["place-bun-cha"],
            "claimIds": ["claim-bun-cha"],
            "reason": "Graph evidence",
        }
    )

    assert requirement.category is ExperienceCategory.meal
    assert requirement.claim_ids == ["claim-bun-cha"]
    assert requirement.evidence_claim_ids == ["claim-bun-cha"]


def test_required_experience_keeps_legacy_evidence_claim_ids_readable() -> None:
    requirement = RequiredExperience.model_validate(
        {
            "requirementId": "req-legacy",
            "theme": "Walk",
            "selectionPolicy": "required_anchor",
            "anchorPlaceIds": ["place-a"],
            "evidenceClaimIds": ["claim-a"],
            "reason": "Legacy payload",
        }
    )

    assert requirement.claim_ids == ["claim-a"]
    assert requirement.model_dump(mode="json", by_alias=True)["claimIds"] == [
        "claim-a"
    ]

