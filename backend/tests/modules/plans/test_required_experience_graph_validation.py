"""Graph validation tests for RequiredExperience."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import RequiredExperience
from app.modules.plans.trip_theme_planner.graph_candidate_projection import project_graph_candidate_catalog
from app.modules.plans.trip_theme_planner.required_experience_validator import (
    RequiredExperienceGraphValidationError,
    validate_required_experience,
)
from .test_trip_theme_graph_candidate_projection import _bundle, _ranked


def _requirement(policy: str, **overrides: Any) -> RequiredExperience:
    payload = {
        "requirementId": "req-1", "theme": "coffee", "selectionPolicy": policy,
        "anchorPlaceIds": ["place-a"] if policy == "required_anchor" else [],
        "candidatePlaceIds": ["place-a", "place-b"] if policy == "choose_one" else [],
        "minimumRequired": 1, "reason": "evidence", "evidenceClaimIds": ["claim-a"],
        "sourceRefs": ["source-a"], "activityId": "activity-a" if policy == "open_candidate" else None,
    }
    payload.update(overrides)
    return RequiredExperience.model_validate(payload)


def _evidence_bundle():
    ranked = _ranked("claim-a", 1, "OFFERS_ACTIVITY", object_id="activity-a", object_type="Activity", activity_id="activity-a", anchor_place_id="place-a", source="source-a")
    ranked2 = _ranked("claim-b", 2, "OFFERS_ACTIVITY", object_id="activity-a", object_type="Activity", activity_id="activity-a", anchor_place_id="place-b", source="source-a")
    return _bundle([ranked, ranked2])


@pytest.mark.parametrize("policy,kwargs", [
    ("required_anchor", {}),
    ("choose_one", {"candidatePlaceIds": ["place-a", "place-b"]}),
    ("open_candidate", {"activityId": "activity-a", "anchorPlaceIds": []}),
])
def test_required_experience_graph_validation_happy_path(policy: str, kwargs: dict[str, Any]) -> None:
    assert validate_required_experience(_requirement(policy, **kwargs), _evidence_bundle())


@pytest.mark.parametrize("policy,kwargs,match", [
    ("required_anchor", {"anchorPlaceIds": ["fake"]}, "anchor"),
    ("choose_one", {"candidatePlaceIds": ["fake", "place-b"]}, "candidate"),
    ("open_candidate", {"activityId": "fake", "anchorPlaceIds": []}, "activity"),
])
def test_required_experience_graph_validation_rejects_fake_ids(policy: str, kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises((RequiredExperienceGraphValidationError, ValidationError), match=match):
        validate_required_experience(_requirement(policy, **kwargs), _evidence_bundle())


def test_required_experience_graph_validation_rejects_unknown_claim_and_source() -> None:
    with pytest.raises(RequiredExperienceGraphValidationError, match="unknown"):
        validate_required_experience(_requirement("required_anchor", evidenceClaimIds=["fake"]), _evidence_bundle())
    with pytest.raises(RequiredExperienceGraphValidationError, match="sourceRefs"):
        validate_required_experience(_requirement("required_anchor", sourceRefs=["fake"]), _evidence_bundle())


def test_required_experience_graph_validation_rejects_conflicted_claim() -> None:
    bundle = _evidence_bundle()
    bundle.conflictedExperiences = [bundle.eligibleExperiences.pop()]
    with pytest.raises(RequiredExperienceGraphValidationError, match="conflicted"):
        validate_required_experience(_requirement("required_anchor"), bundle)
