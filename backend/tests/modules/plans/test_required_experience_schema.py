"""Schema-only contract tests for the requiredExperiences contract.

These tests validate the structural invariants of the new ``RequiredExperience``
schema and the ``TripThemePlanningOutput.requiredExperiences`` field. They do
not touch the TripThemePlanner service, prompt, dependency wiring, or runtime.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningMode,
    RequiredExperience,
    RequiredExperiencePriority,
    RequiredExperienceSelectionPolicy,
    PlaceSelectionInput,
    TripPlanningSpec,
    TripThemePlanningOutput,
)
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.service import PlaceSelectorService


def test_place_selector_contract_accepts_required_experiences() -> None:
    assert "required_experiences" in PlaceSelectionInput.model_fields
    assert "requiredExperiences" in {
        field.alias for field in PlaceSelectionInput.model_fields.values()
    }


class _RequiredPlaceTool:
    def get(self, place_id: str) -> SelectablePlace | None:
        if place_id != "place-bun-cha":
            return None
        return SelectablePlace(
            placeId=place_id,
            name="Bún chả Hà Nội",
            placeType="restaurant",
            regionKey="vn:hanoi",
        )

    def search(self, **kwargs):
        return []


def test_place_selector_resolves_required_anchor_into_selected_place() -> None:
    selection_input = PlaceSelectionInput.model_validate(
        {
            "intent": {"destination": "Hà Nội"},
            "tripSpec": {"days": 1},
            "regionKey": "vn:hanoi",
            "requiredExperiences": [_base_requirement()],
        }
    )

    resolved, unresolved = PlaceSelectorService(
        _RequiredPlaceTool()
    )._required_experience_places(selection_input)

    assert [place.place_id for place in resolved] == ["place-bun-cha"]
    assert resolved[0].must_visit is True
    assert unresolved == []


def _base_requirement(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "requirementId": "req-test-1",
        "theme": "Ẩm thực đường phố",
        "selectionPolicy": "required_anchor",
        "anchorPlaceIds": ["place-bun-cha"],
        "candidatePlaceIds": [],
        "minimumRequired": 1,
        "priority": "must",
        "reason": "Được nhắc tới trong reel và khớp với ngữ cảnh chuyến đi.",
        "evidenceClaimIds": ["claim-1"],
        "sourceRefs": ["https://example.com/reel"],
    }
    payload.update(overrides)
    return payload


def _trip_theme_output(
    **requirement_fields: object,
) -> TripThemePlanningOutput:
    return TripThemePlanningOutput(
        mode=PlanningMode.main,
        trip_spec=TripPlanningSpec(days=2),
        trace=AgentTrace(
            agent=PlanningAgentName.trip_theme_planner,
            status=PlanningAgentStatus.completed,
            summary="stub",
        ),
        required_experiences=[_base_requirement(**requirement_fields)],
    )


def test_required_experience_schema_accepts_required_anchor_payload() -> None:
    requirement = RequiredExperience.model_validate(_base_requirement())

    assert requirement.selection_policy is (
        RequiredExperienceSelectionPolicy.required_anchor
    )
    assert requirement.priority is RequiredExperiencePriority.must
    assert requirement.anchor_place_ids == ["place-bun-cha"]
    assert requirement.minimum_required == 1
    assert requirement.evidence_claim_ids == ["claim-1"]


def test_required_experience_schema_serializes_as_camel_case() -> None:
    requirement = RequiredExperience.model_validate(_base_requirement())

    payload = requirement.model_dump(mode="json", by_alias=True)

    assert payload["requirementId"] == "req-test-1"
    assert payload["selectionPolicy"] == "required_anchor"
    assert payload["anchorPlaceIds"] == ["place-bun-cha"]
    assert payload["minimumRequired"] == 1
    assert payload["evidenceClaimIds"] == ["claim-1"]
    assert payload["sourceRefs"] == ["https://example.com/reel"]


def test_required_experience_schema_requires_anchor_for_required_anchor_policy() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(
            _base_requirement(anchorPlaceIds=[], selectionPolicy="required_anchor"),
        )

    assert "anchorPlaceIds" in str(exc_info.value)


def test_required_experience_schema_requires_candidates_for_choose_one_policy() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(
            _base_requirement(
                candidatePlaceIds=[],
                selectionPolicy="choose_one",
            ),
        )

    assert "candidatePlaceIds" in str(exc_info.value)


def test_required_experience_schema_choose_one_minimum_cannot_exceed_candidates() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(
            _base_requirement(
                selectionPolicy="choose_one",
                candidatePlaceIds=["place-a", "place-b"],
                minimumRequired=3,
            ),
        )

    assert "minimumRequired" in str(exc_info.value)


def test_required_experience_schema_choose_one_minimum_within_candidates() -> None:
    requirement = RequiredExperience.model_validate(
        _base_requirement(
            selectionPolicy="choose_one",
            candidatePlaceIds=["place-a", "place-b", "place-c"],
            minimumRequired=2,
        ),
    )

    assert requirement.minimum_required == 2
    assert len(requirement.candidate_place_ids) == 3


def test_required_experience_schema_open_candidate_requires_activity_id() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(
            _base_requirement(
                selectionPolicy="open_candidate",
                activityId=None,
                anchorPlaceIds=[],
            ),
        )

    assert "activityId" in str(exc_info.value)


def test_required_experience_schema_open_candidate_works_with_activity_id() -> None:
    requirement = RequiredExperience.model_validate(
        _base_requirement(
            selectionPolicy="open_candidate",
            activityId="activity-cafe-hopping",
            anchorPlaceIds=[],
            candidatePlaceIds=[],
        ),
    )

    assert requirement.activity_id == "activity-cafe-hopping"
    assert requirement.selection_policy is (
        RequiredExperienceSelectionPolicy.open_candidate
    )


def test_required_experience_schema_rejects_empty_evidence_claim_ids() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(_base_requirement(evidenceClaimIds=[]))

    assert "evidenceClaimIds" in str(exc_info.value)


def test_required_experience_schema_rejects_day_route_allocation_fields() -> None:
    with pytest.raises(ValidationError):
        RequiredExperience.model_validate(
            _base_requirement(day=1, route="loop", allocation="slot"),
        )


def test_required_experience_schema_rejects_priority_other_than_must() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RequiredExperience.model_validate(_base_requirement(priority="should"))

    assert "priority" in str(exc_info.value)


def test_trip_theme_planning_output_default_required_experiences_is_empty() -> None:
    output = TripThemePlanningOutput(
        mode=PlanningMode.main,
        trip_spec=TripPlanningSpec(days=2),
        trace=AgentTrace(
            agent=PlanningAgentName.trip_theme_planner,
            status=PlanningAgentStatus.completed,
            summary="stub",
        ),
    )

    assert output.required_experiences == []
    payload = output.model_dump(mode="json", by_alias=True)
    assert payload["requiredExperiences"] == []


def test_trip_theme_planning_output_deserializes_legacy_payload_without_required_experiences() -> (
    None
):
    payload = {
        "mode": "main",
        "tripSpec": {"days": 2},
        "tripThemesReady": True,
        "tripThemes": [],
        "assumptions": [],
        "warnings": [],
        "trace": {
            "agent": "trip_theme_planner",
            "status": "completed",
            "summary": "legacy",
        },
    }

    output = TripThemePlanningOutput.model_validate(payload)

    assert output.required_experiences == []
    assert output.trip_themes == []


def test_trip_theme_planning_output_serializes_required_experiences_as_camel_case() -> (
    None
):
    output = _trip_theme_output()

    payload = output.model_dump(mode="json", by_alias=True)

    assert "requiredExperiences" in payload
    assert isinstance(payload["requiredExperiences"], list)
    assert payload["requiredExperiences"][0]["requirementId"] == "req-test-1"
    assert (
        payload["requiredExperiences"][0]["selectionPolicy"] == "required_anchor"
    )
    assert (
        payload["requiredExperiences"][0]["anchorPlaceIds"] == ["place-bun-cha"]
    )


def test_trip_theme_planning_output_exposes_snake_case_on_python_side() -> None:
    output = _trip_theme_output()

    requirement = output.required_experiences[0]
    assert requirement.requirement_id == "req-test-1"
    assert requirement.selection_policy is (
        RequiredExperienceSelectionPolicy.required_anchor
    )
    assert requirement.anchor_place_ids == ["place-bun-cha"]
    assert requirement.minimum_required == 1
    assert requirement.evidence_claim_ids == ["claim-1"]
    assert requirement.source_refs == ["https://example.com/reel"]


def test_trip_theme_planning_output_rejects_day_route_allocation_at_top_level() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        TripThemePlanningOutput.model_validate(
            {
                "mode": "main",
                "tripSpec": {"days": 2},
                "trace": {
                    "agent": "trip_theme_planner",
                    "status": "completed",
                    "summary": "stub",
                },
                "day": 1,
            },
        )

    assert "day" in str(exc_info.value)


def test_trip_theme_planning_output_rejects_day_route_allocation_inside_requirement() -> (
    None
):
    payload = {
        "mode": "main",
        "tripSpec": {"days": 2},
        "trace": {
            "agent": "trip_theme_planner",
            "status": "completed",
            "summary": "stub",
        },
        "requiredExperiences": [
            {
                **_base_requirement(),
                "scheduledDay": 2,
            },
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        TripThemePlanningOutput.model_validate(payload)

    assert "scheduledDay" in str(exc_info.value)
