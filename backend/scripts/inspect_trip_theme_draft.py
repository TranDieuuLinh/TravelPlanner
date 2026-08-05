#!/usr/bin/env python3
"""Inspect the TripTheme planner draft and requiredExperiences round-trip.

This CLI exercises the same code path as ``TripThemePlannerService`` but uses
scripted fake LLM responses and a fake graph research orchestrator so we can
inspect each stage deterministically without a configured LLM provider.

Example:

    python scripts/inspect_trip_theme_draft.py \\
        --policy required_anchor \\
        --days 2 \\
        --pretty
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

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
from app.modules.plans.dto.agent_contracts import TripPlanningSpec
from app.modules.plans.planner.region_context import PlannerStatisticsProvider  # noqa: F401  (kept for future fallback)
from app.modules.plans.trip_theme_planner.region_context import (
    PlannerStatisticsProvider as _TripThemePlannerStatisticsProvider,
)
from app.modules.plans.trip_theme_planner.service import TripThemePlannerService


class _StatisticsProviderBase:
    pass


# Re-export the protocol so the script-level ``class Foo(_StatisticsProviderBase)``
# below satisfies the structural type checker.
class PlannerStatisticsProvider(_StatisticsProviderBase, _TripThemePlannerStatisticsProvider):  # type: ignore[misc]
    """Inherit-from-protocol helper so ``_FakeStatisticsProvider`` is typed."""


def _entity(
    entity_id: str,
    name: str,
    entity_type: str,
    status: str = "verified",
) -> EntitySummary:
    return EntitySummary(id=entity_id, name=name, type=entity_type, status=status)


def _claim(
    claim_id: str,
    *,
    predicate: str = "OFFERS_ACTIVITY",
    object_id: str,
    object_type: str,
    object_name: str,
    activity_id: str | None,
    activity_name: str | None,
    anchor_place_id: str,
    anchor_place_name: str,
    source: str,
    priority: RecommendationPriority,
) -> GraphEvidenceClaim:
    activity = (
        _entity(activity_id, activity_name or activity_id, "Activity")
        if activity_id
        else None
    )
    anchor_place = _entity(anchor_place_id, anchor_place_name, "TravelPlace")
    path = [
        "area_hanoi",
        predicate,
        anchor_place_id,
        "OFFERS_ACTIVITY",
        activity_id or object_id,
    ]
    return GraphEvidenceClaim(
        claimId=claim_id,
        subject=_entity("area_hanoi", "Area Hanoi", "AreaAdm1"),
        predicate=predicate,
        object=_entity(object_id, object_name, object_type),
        path=path,
        anchorPlace=anchor_place,
        activity=activity,
        recommendations=[Recommendation(priority=priority)],
        evidence=[EdgeEvidence(source=source, recommendations=[])],
        trust=TrustLevel.SOURCE_BACKED,
    )


def _graph_bundle() -> TripResearchBundle:
    coffee_claim = _claim(
        claim_id="claim-coffee",
        object_id="activity-coffee",
        object_type="Activity",
        object_name="Coffee Tour",
        activity_id="activity-coffee",
        activity_name="Coffee Tour",
        anchor_place_id="place-cafe-giang",
        anchor_place_name="Cafe Giảng",
        source="https://example.com/cafe",
        priority=RecommendationPriority.MUST,
    )
    cooking_a = _claim(
        claim_id="claim-cooking-a",
        object_id="activity-cooking",
        object_type="Activity",
        object_name="Cooking Class",
        activity_id="activity-cooking",
        activity_name="Cooking Class",
        anchor_place_id="place-cooking-a",
        anchor_place_name="Cooking A",
        source="https://example.com/cooking",
        priority=RecommendationPriority.MUST,
    )
    cooking_b = _claim(
        claim_id="claim-cooking-b",
        object_id="activity-cooking",
        object_type="Activity",
        object_name="Cooking Class",
        activity_id="activity-cooking",
        activity_name="Cooking Class",
        anchor_place_id="place-cooking-b",
        anchor_place_name="Cooking B",
        source="https://example.com/cooking",
        priority=RecommendationPriority.RECOMMENDED,
    )
    return TripResearchBundle(
        scope=ScopeResolveOutput(),
        eligibleExperiences=[
            RankedExperience(
                claim=coffee_claim, fit=_fit(), rank=1, rankReasons=["rank_1"]
            ),
            RankedExperience(
                claim=cooking_a, fit=_fit(), rank=2, rankReasons=["rank_2"]
            ),
            RankedExperience(
                claim=cooking_b, fit=_fit(), rank=3, rankReasons=["rank_3"]
            ),
        ],
        graphSnapshot=GraphSnapshot(timestamp="2026-08-04T00:00:00Z"),
    )


def _fit() -> FitResult:
    return FitResult(
        status=CheckStatus.SUPPORTED,
        hasHardConflict=False,
        dimensionCount=2,
    )


class _FakeGraphOrchestrator:
    def __init__(self, bundle: TripResearchBundle) -> None:
        self._bundle = bundle

    def research(self, _input_data) -> TripResearchBundle:
        return self._bundle


class _FakeStatisticsProvider(PlannerStatisticsProvider):
    def get_for_planner(self, region_key: str, *, force: bool = False):  # type: ignore[override]
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
                    "areaProfiles": [],
                    "plannerSignals": {
                        "dominantTags": ["food", "culture"],
                        "strongDayParts": ["morning", "afternoon"],
                        "weakDayParts": ["evening"],
                        "candidateAreas": [],
                    },
                }
            ],
            snapshot_id="snapshot-cli",
            catalog_version=1,
            algorithm_version="auto_statistics_v2_1",
            generated_at="2026-08-04T00:00:00+00:00",
            source_fingerprint="cli",
        )


class _ScriptedLLM:
    """LLM that records each prompt/payload and returns a configured draft.

    Set ``mode`` to ``"valid"`` to return a valid draft, or ``"invalid"`` to
    return an invalid ``requiredExperiences`` payload, or ``"always_invalid"``
    to keep returning the invalid draft through every repair attempt.
    """

    def __init__(
        self,
        *,
        mode: str,
        selection_policy: str,
        requirement_id: str = "req-cli",
    ) -> None:
        self.mode = mode
        self.selection_policy = selection_policy
        self.requirement_id = requirement_id
        self.research_calls = 0
        self.macro_calls = 0
        self.system_prompts: list[str] = []
        self.payloads: list[str] = []

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        stage = envelope["stage"]
        if stage == "research":
            self.research_calls += 1
            return json.dumps(
                {
                    "journeyStyle": "local_base",
                    "varietyStrategy": "Inspect the catalog with each policy.",
                    "themeQueries": [
                        {
                            "theme": "Coffee",
                            "capabilities": ["coffee"],
                            "rationale": "verify coffee",
                        },
                        {
                            "theme": "Cooking",
                            "capabilities": ["food"],
                            "rationale": "verify cooking",
                        },
                    ],
                    "expandBeyondRoot": False,
                    "nearbyCapabilities": [],
                    "maxDistanceKm": 100,
                },
                ensure_ascii=False,
            )
        self.macro_calls += 1
        self.system_prompts.append(system_prompt)
        self.payloads.append(user_payload)
        return _scripted_draft(
            mode=self.mode,
            selection_policy=self.selection_policy,
            requirement_id=self.requirement_id,
            repair=stage == "trip_theme_plan_repair",
        )


def _scripted_draft(
    *,
    mode: str,
    selection_policy: str,
    requirement_id: str,
    repair: bool,
) -> str:
    """Build the draft JSON returned by the fake LLM."""

    if mode == "always_invalid" or (mode == "invalid" and not repair):
        required = [{
            "requirementId": requirement_id,
            "theme": "Coffee tour",
            "selectionPolicy": selection_policy,
            "anchorPlaceIds": ["place-cafe-giang"] if selection_policy == "required_anchor" else [],
            "candidatePlaceIds": ["place-cooking-a"] if selection_policy == "choose_one" else [],
            "activityId": None,
            "minimumRequired": 1,
            "priority": "must",
            "reason": "Invalid: fabricated claim id is not in the catalog.",
            "evidenceClaimIds": ["claim-fabricated-not-in-catalog"],
            "sourceRefs": ["https://example.com/cafe"],
        }]
    else:
        if selection_policy == "required_anchor":
            required = [{
                "requirementId": requirement_id,
                "theme": "Coffee tour",
                "selectionPolicy": "required_anchor",
                "anchorPlaceIds": ["place-cafe-giang"],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Anchor the coffee tour at Cafe Giảng.",
                "evidenceClaimIds": ["claim-coffee"],
                "sourceRefs": ["https://example.com/cafe"],
            }]
        elif selection_policy == "choose_one":
            required = [{
                "requirementId": requirement_id,
                "theme": "Cooking class",
                "selectionPolicy": "choose_one",
                "anchorPlaceIds": [],
                "candidatePlaceIds": ["place-cooking-a", "place-cooking-b"],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "Pick one of two cooking class venues.",
                "evidenceClaimIds": ["claim-cooking-a", "claim-cooking-b"],
                "sourceRefs": ["https://example.com/cooking"],
            }]
        else:
            required = [{
                "requirementId": requirement_id,
                "theme": "Coffee tour",
                "selectionPolicy": "open_candidate",
                "activityId": "activity-coffee",
                "anchorPlaceIds": [],
                "candidatePlaceIds": [],
                "minimumRequired": 1,
                "priority": "must",
                "reason": "PlaceSelector will pick any coffee tour venue.",
                "evidenceClaimIds": ["claim-coffee"],
                "sourceRefs": ["https://example.com/cafe"],
            }]
    return json.dumps(
        {
            "tripThemes": [
                {
                    "theme": "Coffee tour",
                    "focusTags": ["coffee"],
                    "minimumActivities": 1,
                    "targetRegionKeys": ["vn,ha-noi"],
                },
            ],
            "requiredExperiences": required,
            "assumptions": ["Fake LLM response for inspection."],
            "warnings": [],
        },
        ensure_ascii=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect_trip_theme_draft",
        description="Inspect the TripTheme planner round-trip with a fake LLM.",
    )
    parser.add_argument(
        "--mode",
        choices=["valid", "invalid", "always_invalid"],
        default="valid",
        help="How the fake LLM should respond on the macro stage.",
    )
    parser.add_argument(
        "--policy",
        choices=["required_anchor", "choose_one", "open_candidate"],
        default="required_anchor",
        help="selectionPolicy the fake LLM uses when emitting valid drafts.",
    )
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--region-key", default="vn,ha-noi")
    parser.add_argument("--pretty", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> int:
    llm = _ScriptedLLM(mode=args.mode, selection_policy=args.policy)
    service = TripThemePlannerService(
        statistics_provider=_FakeStatisticsProvider(),
        llm=llm,
        graph_research_orchestrator=_FakeGraphOrchestrator(_graph_bundle()),
    )
    intent = TravelIntent(
        destination="Hà Nội",
        days=args.days,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["coffee", "food"],
    )
    trip_spec = TripPlanningSpec(days=args.days)
    try:
        output = await service.create_trip_themes(
            intent,
            trip_spec=trip_spec,
            region_key=args.region_key,
            selected_places=[],
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    macro_payloads = [
        {
            "stage": json.loads(payload).get("stage"),
            "graphCandidateCatalog": json.loads(payload).get(
                "graphCandidateCatalog"
            ),
        }
        for payload in llm.payloads
    ]
    summary = {
        "tripThemesReady": output.trip_themes_ready,
        "tripThemes": [
            theme.model_dump(mode="json", by_alias=True)
            for theme in output.trip_themes
        ],
        "requiredExperiences": [
            exp.model_dump(mode="json", by_alias=True)
            for exp in output.required_experiences
        ],
        "assumptions": output.assumptions,
        "warnings": output.warnings,
        "trace": output.trace.model_dump(mode="json", by_alias=True),
        "macroPrompts": len(llm.system_prompts),
        "macroCalls": llm.macro_calls,
        "payloads": macro_payloads,
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
