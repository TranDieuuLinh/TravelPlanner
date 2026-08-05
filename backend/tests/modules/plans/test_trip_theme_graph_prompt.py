"""TripTheme planner tests for graph-bounded ``requiredExperiences`` selection.

Scope (MICRO-TASK 5.7):
- The TripTheme LLM is constrained to pick ``requiredExperiences`` IDs from the
  bounded ``graphCandidateCatalog`` delivered with the trip theme payload.
- Each of the three ``selectionPolicy`` values is exercised end-to-end.
- Invalid IDs (Place, Activity, claim) are rejected by the repair loop and the
  LLM is asked to repair.
- The repair loop stops after three failed attempts.
- Graph research replaces the legacy research LLM call, so the happy path uses
  exactly one LLM call.

The fake LLM, fake graph orchestrator, and fake statistics provider keep the
tests deterministic and isolated from the production wiring, which is not
exercised here.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.modules.knowledge_graph.research import (
    CheckStatus,
    FitResult,
    GraphEvidenceClaim,
    GraphSnapshot,
    RankedExperience,
    ScopeResolveOutput,
    TripResearchBundle,
    TrustLevel,
)
from app.modules.knowledge_graph.research.schema import (
    EdgeEvidence,
    EntitySummary,
    Recommendation,
    RecommendationPriority,
)
from app.modules.plans.domain.entities import TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext, TripPlanningSpec
from app.modules.plans.trip_theme_planner.service import TripThemePlannerService
from app.modules.preferences.schema import LongTermPreferenceProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entity(
    entity_id: str,
    name: str,
    entity_type: str,
    status: str = "verified",
) -> EntitySummary:
    return EntitySummary(id=entity_id, name=name, type=entity_type, status=status)


def _fit() -> FitResult:
    return FitResult(
        status=CheckStatus.SUPPORTED,
        hasHardConflict=False,
        dimensionCount=2,
    )


def _claim(
    claim_id: str,
    *,
    predicate: str = "OFFERS_ACTIVITY",
    subject_id: str = "area_hanoi",
    object_id: str,
    object_type: str,
    object_name: str,
    activity_id: str | None,
    activity_name: str | None,
    anchor_place_id: str,
    anchor_place_name: str = "Anchor Place",
    source: str = "https://example.com/source",
    priority: RecommendationPriority = RecommendationPriority.MUST,
    time_slots: list[str | dict] | None = None,
    recommended_visit_minutes: int | None = None,
) -> GraphEvidenceClaim:
    activity = None
    if activity_id is not None:
        activity = _entity(activity_id, activity_name or activity_id, "Activity")

    anchor_place = _entity(anchor_place_id, anchor_place_name, "TravelPlace")

    path = [
        subject_id,
        predicate,
        anchor_place_id,
        "OFFERS_ACTIVITY",
        activity_id or object_id,
    ]

    return GraphEvidenceClaim(
        claimId=claim_id,
        subject=_entity(subject_id, "Area Hanoi", "AreaAdm1"),
        predicate=predicate,
        object=_entity(object_id, object_name, object_type),
        path=path,
        anchorPlace=anchor_place,
        activity=activity,
        recommendations=[
            Recommendation(
                priority=priority,
                timeSlots=time_slots or [],
                recommendedVisitMinutes=recommended_visit_minutes,
            )
        ],
        evidence=[EdgeEvidence(source=source, recommendations=[])],
        trust=TrustLevel.SOURCE_BACKED,
    )


def _ranked(claim: GraphEvidenceClaim, rank: int) -> RankedExperience:
    return RankedExperience(
        claim=claim,
        fit=_fit(),
        rank=rank,
        rankReasons=[f"rank_{rank}"],
    )


def _graph_bundle() -> TripResearchBundle:
    """Bundle containing three graph candidates used by the test fixtures."""

    coffee_claim = _claim(
        claim_id="claim-coffee-tour",
        predicate="SPECIAL_EXPERIENCE",
        object_id="activity-coffee-tour",
        object_type="Activity",
        object_name="Coffee Tour",
        activity_id="activity-coffee-tour",
        activity_name="Coffee Tour",
        anchor_place_id="place-cafe-giang",
        anchor_place_name="Cafe Giảng",
        source="https://example.com/cafe-source",
        time_slots=["19:00-21:00"],
        recommended_visit_minutes=60,
    )
    cooking_claim_a = _claim(
        claim_id="claim-cooking-a",
        object_id="activity-cooking-class",
        object_type="Activity",
        object_name="Cooking Class A",
        activity_id="activity-cooking-class",
        activity_name="Cooking Class",
        anchor_place_id="place-cooking-a",
        anchor_place_name="Cooking A",
        source="https://example.com/cooking-source",
        priority=RecommendationPriority.MUST,
    )
    cooking_claim_b = _claim(
        claim_id="claim-cooking-b",
        object_id="activity-cooking-class",
        object_type="Activity",
        object_name="Cooking Class B",
        activity_id="activity-cooking-class",
        activity_name="Cooking Class",
        anchor_place_id="place-cooking-b",
        anchor_place_name="Cooking B",
        source="https://example.com/cooking-source",
        priority=RecommendationPriority.RECOMMENDED,
    )

    return TripResearchBundle(
        scope=ScopeResolveOutput(),
        eligibleExperiences=[
            _ranked(coffee_claim, 1),
            _ranked(cooking_claim_a, 2),
            _ranked(cooking_claim_b, 3),
        ],
        graphSnapshot=GraphSnapshot(timestamp="2026-08-04T00:00:00Z"),
    )


class _RecordingGraphOrchestrator:
    def __init__(self, bundle: TripResearchBundle) -> None:
        self._bundle = bundle
        self.calls: int = 0

    def research(self, input_data) -> TripResearchBundle:
        self.calls += 1
        return self._bundle


class _FakeStatisticsProvider:
    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> object:
        from app.modules.places.auto_statistics.service import (
            PlannerRegionStatisticsResult,
        )

        return PlannerRegionStatisticsResult(
            status="cached",
            region_key=region_key,
            regions=[
                {
                    "regionKey": region_key,
                    "placeCount": 20,
                    "activePlaceCount": 20,
                    "countsByType": {"museum": 4, "restaurant": 8},
                    "tagCounts": {"culture": 4, "food": 8},
                    "timeOfDayCoverage": {
                        "morning": 10,
                        "lunch": 8,
                        "afternoon": 10,
                        "evening": 3,
                        "placesWithKnownHours": 12,
                    },
                    "dataQuality": {
                        "missingOpeningHours": 4,
                        "staleOperationalData": 0,
                    },
                    "areaProfiles": [
                        {
                            "regionKey": "vn,ha-noi,hoan-kiem",
                            "placeCount": 12,
                            "topTags": ["food", "culture"],
                        }
                    ],
                    "plannerSignals": {
                        "dominantTags": ["food", "culture"],
                        "strongDayParts": ["morning", "afternoon"],
                        "weakDayParts": ["evening"],
                        "candidateAreas": [
                            {
                                "regionKey": "vn,ha-noi,hoan-kiem",
                                "placeCount": 12,
                                "topTags": ["food", "culture"],
                            }
                        ],
                    },
                }
            ],
            snapshot_id="snapshot-5-5",
            catalog_version=5,
            algorithm_version="auto_statistics_v2_1",
            generated_at="2026-08-04T00:00:00+00:00",
            source_fingerprint="fingerprint",
        )


def _intent() -> TravelIntent:
    return TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )


def _intent_without_interests() -> TravelIntent:
    return TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=[],
    )


# ---------------------------------------------------------------------------
# Fake LLM clients
# ---------------------------------------------------------------------------


class _GraphThemeScriptedLLM:
    """Fake LLM that returns a trip theme draft with the supplied
    ``requiredExperiences`` payload and remembers every macro call."""

    def __init__(
        self,
        *,
        trip_themes: list[dict],
        required_experiences: list[dict],
        assumptions: list[str] | None = None,
    ) -> None:
        self._trip_themes = trip_themes
        self._required_experiences = required_experiences
        self._assumptions = assumptions or ["Generated by fake LLM."]
        self.macro_calls = 0
        self.macro_payloads: list[str] = []
        self.system_prompts: list[str] = []

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        self.macro_calls += 1
        self.system_prompts.append(system_prompt)
        self.macro_payloads.append(user_payload)
        return json.dumps(
            {
                "tripThemes": self._trip_themes,
                "requiredExperiences": self._required_experiences,
                "assumptions": self._assumptions,
                "warnings": [],
            },
            ensure_ascii=False,
        )


class _InvalidIdRepairingLLM(_GraphThemeScriptedLLM):
    """LLM that returns an invalid ``requiredExperiences`` payload on the first
    call and a valid one on the repair attempt."""

    def __init__(
        self,
        *,
        valid_required_experiences: list[dict],
        invalid_required_experiences: list[dict],
        trip_themes: list[dict],
    ) -> None:
        super().__init__(
            trip_themes=trip_themes,
            required_experiences=invalid_required_experiences,
        )
        self._valid_required_experiences = valid_required_experiences

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        self.macro_calls += 1
        self.system_prompts.append(system_prompt)
        self.macro_payloads.append(user_payload)
        if envelope["stage"] == "trip_theme_plan_repair":
            return json.dumps(
                {
                    "tripThemes": self._trip_themes,
                    "requiredExperiences": self._valid_required_experiences,
                    "assumptions": self._assumptions,
                    "warnings": [],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "tripThemes": self._trip_themes,
                "requiredExperiences": self._required_experiences,
                "assumptions": self._assumptions,
                "warnings": [],
            },
            ensure_ascii=False,
        )


class _AlwaysInvalidLLM(_GraphThemeScriptedLLM):
    """LLM that keeps returning an invalid ``requiredExperiences`` payload."""

    def __init__(
        self, *, invalid_required_experiences: list[dict], trip_themes: list[dict]
    ) -> None:
        super().__init__(
            trip_themes=trip_themes,
            required_experiences=invalid_required_experiences,
        )

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        self.macro_calls += 1
        self.system_prompts.append(system_prompt)
        self.macro_payloads.append(user_payload)
        return json.dumps(
            {
                "tripThemes": self._trip_themes,
                "requiredExperiences": self._required_experiences,
                "assumptions": self._assumptions,
                "warnings": [],
            },
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service(llm) -> tuple[TripThemePlannerService, _RecordingGraphOrchestrator]:
    orchestrator = _RecordingGraphOrchestrator(_graph_bundle())
    service = TripThemePlannerService(
        statistics_provider=_FakeStatisticsProvider(),
        llm=llm,
        graph_research_orchestrator=orchestrator,
    )
    return service, orchestrator


def _trip_themes() -> list[dict]:
    return [
        {
            "theme": "Coffee tour",
            "focusTags": ["coffee"],
            "minimumActivities": 1,
            "targetRegionKeys": ["vn,ha-noi"],
        },
        {
            "theme": "Cooking class",
            "focusTags": ["food"],
            "minimumActivities": 1,
            "targetRegionKeys": ["vn,ha-noi"],
        },
    ]


# ---------------------------------------------------------------------------
# Selection policies
# ---------------------------------------------------------------------------


class TestRequiredAnchorSelection:
    def test_required_anchor_returns_validated_required_experience(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[
                {
                    "requirementId": "req-coffee",
                    "theme": "Coffee tour",
                    "selectionPolicy": "required_anchor",
                    "anchorPlaceIds": ["place-cafe-giang"],
                    "candidatePlaceIds": [],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Anchor coffee tour at Cafe Giảng.",
                    "evidenceClaimIds": ["claim-coffee-tour"],
                    "sourceRefs": ["https://example.com/cafe-source"],
                    # Backend validation must replace model-echoed timing with
                    # the recommendation attached to the validated graph edge.
                    "preferredTimeWindows": [
                        {"start": "09:00", "end": "10:00"}
                    ],
                    "recommendedVisitMinutes": 15,
                }
            ],
        )
        service, orchestrator = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        output = asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        assert output.trip_themes_ready is True
        assert len(output.required_experiences) == 1
        requirement = output.required_experiences[0]
        assert requirement.selection_policy.value == "required_anchor"
        assert requirement.anchor_place_ids == ["place-cafe-giang"]
        assert "claim-coffee-tour" in requirement.evidence_claim_ids
        assert requirement.model_dump(mode="json", by_alias=True)[
            "preferredTimeWindows"
        ] == [{"start": "19:00", "end": "21:00"}]
        assert requirement.recommended_visit_minutes == 60
        assert llm.macro_calls == 1
        assert orchestrator.calls == 1


class TestChooseOneSelection:
    def test_choose_one_returns_validated_required_experience(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[
                {
                    "requirementId": "req-cooking",
                    "theme": "Cooking class",
                    "selectionPolicy": "choose_one",
                    "anchorPlaceIds": [],
                    "candidatePlaceIds": [
                        "place-cooking-a",
                        "place-cooking-b",
                    ],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Pick one of the cooking class venues.",
                    "evidenceClaimIds": [
                        "claim-cooking-a",
                        "claim-cooking-b",
                    ],
                    "sourceRefs": ["https://example.com/cooking-source"],
                }
            ],
        )
        service, _ = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        output = asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        assert output.trip_themes_ready is True
        requirement = output.required_experiences[0]
        assert requirement.selection_policy.value == "choose_one"
        assert set(requirement.candidate_place_ids) == {
            "place-cooking-a",
            "place-cooking-b",
        }
        assert set(requirement.evidence_claim_ids) == {
            "claim-cooking-a",
            "claim-cooking-b",
        }


class TestOpenCandidateSelection:
    def test_open_candidate_returns_validated_required_experience(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[
                {
                    "requirementId": "req-coffee-open",
                    "theme": "Coffee tour",
                    "selectionPolicy": "open_candidate",
                    "activityId": "activity-coffee-tour",
                    "anchorPlaceIds": [],
                    "candidatePlaceIds": [],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Let PlaceSelector pick any coffee tour venue.",
                    "evidenceClaimIds": ["claim-coffee-tour"],
                    "sourceRefs": ["https://example.com/cafe-source"],
                }
            ],
        )
        service, _ = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        output = asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        assert output.trip_themes_ready is True
        requirement = output.required_experiences[0]
        assert requirement.selection_policy.value == "open_candidate"
        assert requirement.activity_id == "activity-coffee-tour"


# ---------------------------------------------------------------------------
# Repair loop
# ---------------------------------------------------------------------------


class TestInvalidIdRepair:
    def test_invalid_claim_id_is_repaired_on_second_call(self) -> None:
        valid_required_experiences = [
            {
                "requirementId": "req-coffee-repaired",
                "theme": "Coffee tour",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Anchor coffee tour at Cafe Giảng after repair.",
                "evidenceClaimIds": ["claim-coffee-tour"],
                "sourceRefs": ["https://example.com/cafe-source"],
            }
        ]
        llm = _InvalidIdRepairingLLM(
            valid_required_experiences=valid_required_experiences,
            invalid_required_experiences=[
                {
                    "requirementId": "req-coffee-bad",
                    "theme": "Coffee tour",
                    "selectionPolicy": "required_anchor",
                    "anchorPlaceIds": ["place-cafe-giang"],
                    "candidatePlaceIds": [],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Anchor with a fabricated claim id.",
                    "evidenceClaimIds": ["claim-fabricated"],
                    "sourceRefs": ["https://example.com/cafe-source"],
                }
            ],
            trip_themes=_trip_themes(),
        )
        service, _ = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        output = asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        assert output.trip_themes_ready is True
        assert llm.macro_calls == 2
        assert "repairAttempts=1" in output.trace.notes
        assert len(output.required_experiences) == 1
        assert output.required_experiences[0].requirement_id == "req-coffee-repaired"
        assert "claim-coffee-tour" in output.required_experiences[0].evidence_claim_ids


class TestThreeFailedRepairs:
    def test_stops_after_three_failed_repairs(self) -> None:
        invalid_required_experiences = [
            {
                "requirementId": "req-coffee-fake",
                "theme": "Coffee tour",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Keeps fabricating claim ids.",
                "evidenceClaimIds": ["claim-not-in-catalog"],
                "sourceRefs": ["https://example.com/cafe-source"],
            }
        ]
        llm = _AlwaysInvalidLLM(
            invalid_required_experiences=invalid_required_experiences,
            trip_themes=_trip_themes(),
        )
        service, _ = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        with pytest.raises(RuntimeError, match="after 3 repair attempts"):
            asyncio.run(
                service.create_trip_themes(
                    _intent(),
                    trip_spec=TripPlanningSpec(days=2),
                    region_key="vn,ha-noi",
                    selected_places=[],
                )
            )

        # initial macro call + 3 repair attempts
        assert llm.macro_calls == 4


# ---------------------------------------------------------------------------
# Prompt exposes graph candidate catalog
# ---------------------------------------------------------------------------


class TestGraphCatalogInPayload:
    def test_graph_candidate_catalog_is_passed_in_payload(self) -> None:
        valid_required_experiences = [
            {
                "requirementId": "req-coffee-payload",
                "theme": "Coffee tour",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Coffee tour anchor.",
                "evidenceClaimIds": ["claim-coffee-tour"],
                "sourceRefs": ["https://example.com/cafe-source"],
            }
        ]
        invalid_required_experiences = [
            {
                "requirementId": "req-coffee-bad",
                "theme": "Coffee tour",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Anchor with a fabricated claim id.",
                "evidenceClaimIds": ["claim-fabricated"],
                "sourceRefs": ["https://example.com/cafe-source"],
            }
        ]
        llm = _InvalidIdRepairingLLM(
            valid_required_experiences=valid_required_experiences,
            invalid_required_experiences=invalid_required_experiences,
            trip_themes=_trip_themes(),
        )
        service, _ = _build_service(llm)

        from app.modules.plans.dto.agent_contracts import TripPlanningSpec

        asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        macro_payload = json.loads(llm.macro_payloads[0])
        assert macro_payload["themeSelectionPolicy"]["selectionMode"] == (
            "current_trip_intent"
        )
        catalog = macro_payload["graphCandidateCatalog"]["candidates"]
        activity_ids = {candidate["activityId"] for candidate in catalog}
        place_ids = {
            anchor
            for candidate in catalog
            for anchor in candidate["anchorPlaceIds"]
        }
        assert "activity-coffee-tour" in activity_ids
        assert "activity-cooking-class" in activity_ids
        assert "place-cafe-giang" in place_ids
        assert "Trip Theme Planner" in llm.system_prompts[0]
        assert "graphCandidateCatalog" in llm.system_prompts[0]
        # Repair payload should also include the bounded catalog so the LLM
        # can pick only IDs from it during the repair attempt.
        assert len(llm.macro_payloads) >= 2
        repair_payload = json.loads(llm.macro_payloads[1])
        assert repair_payload["stage"] == "trip_theme_plan_repair"
        assert "graphCandidateCatalog" in repair_payload
        assert "claim-coffee-tour" in {
            claim
            for candidate in repair_payload["graphCandidateCatalog"]["candidates"]
            for claim in candidate["claimIds"]
        }


class TestGraphCutoverEvaluations:
    def test_destination_defaults_require_trusted_special_experience(self) -> None:
        valid_fallback = [
            {
                "requirementId": "req-default-coffee",
                "theme": "Trải nghiệm cà phê đặc trưng",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Không có sở thích cá nhân nên dùng special experience.",
                "evidenceClaimIds": ["claim-coffee-tour"],
                "sourceRefs": ["https://example.com/cafe-source"],
            }
        ]
        llm = _InvalidIdRepairingLLM(
            valid_required_experiences=valid_fallback,
            invalid_required_experiences=[],
            trip_themes=_trip_themes(),
        )
        service, _ = _build_service(llm)

        output = asyncio.run(
            service.create_trip_themes(
                _intent_without_interests(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        policy = json.loads(llm.macro_payloads[0])["themeSelectionPolicy"]
        assert policy["selectionMode"] == "destination_special_experiences"
        assert llm.macro_calls == 2
        assert output.required_experiences[0].requirement_id == "req-default-coffee"

    def test_confirmed_places_take_priority_over_long_term_profile(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[],
        )
        service, _ = _build_service(llm)

        asyncio.run(
            service.create_trip_themes(
                _intent_without_interests(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[
                    SelectedPlaceContext(
                        name="Văn Miếu",
                        placeId="place-van-mieu",
                    )
                ],
                preference_profile=LongTermPreferenceProfile(
                    explicit=["coffee"]
                ),
            )
        )

        policy = json.loads(llm.macro_payloads[0])["themeSelectionPolicy"]
        assert policy["selectionMode"] == "confirmed_places"

    def test_long_term_profile_is_used_before_destination_defaults(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[],
        )
        service, _ = _build_service(llm)

        asyncio.run(
            service.create_trip_themes(
                _intent_without_interests(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
                preference_profile=LongTermPreferenceProfile(
                    explicit=["coffee"]
                ),
            )
        )

        policy = json.loads(llm.macro_payloads[0])["themeSelectionPolicy"]
        assert policy["selectionMode"] == "long_term_profile"

    def test_empty_coverage_sends_empty_catalog_with_one_llm_call(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[],
        )
        empty_bundle = TripResearchBundle(
            scope=ScopeResolveOutput(),
            eligibleExperiences=[],
            warnings=["GRAPH_EXPERIENCE_COVERAGE_EMPTY"],
            graphSnapshot=GraphSnapshot(timestamp="2026-08-05T00:00:00Z"),
        )
        orchestrator = _RecordingGraphOrchestrator(empty_bundle)
        service = TripThemePlannerService(
            statistics_provider=_FakeStatisticsProvider(),
            llm=llm,
            graph_research_orchestrator=orchestrator,
        )

        output = asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

        assert output.required_experiences == []
        assert llm.macro_calls == 1
        assert orchestrator.calls == 1
        assert json.loads(llm.macro_payloads[0])["graphCandidateCatalog"] == {
            "candidates": []
        }

    def test_private_notes_never_enter_llm_payload(self) -> None:
        llm = _GraphThemeScriptedLLM(
            trip_themes=_trip_themes(),
            required_experiences=[],
        )
        service, _ = _build_service(llm)
        secret = "PRIVATE-NOTE-MUST-NOT-CROSS"

        asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[
                    SelectedPlaceContext(
                        name="Văn Miếu",
                        placeId="place-van-mieu",
                        personalNotes=secret,
                        notes=secret,
                    )
                ],
            )
        )

        assert secret not in llm.macro_payloads[0]
        selected = json.loads(llm.macro_payloads[0])["plannerInput"]["selectedPlaces"]
        assert "personalNotes" not in selected[0]
        assert "notes" not in selected[0]
