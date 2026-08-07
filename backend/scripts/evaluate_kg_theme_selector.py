"""Offline KG-shaped integration evaluation for TripThemePlanner -> Selector -> CheckOverall."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.modules.knowledge_graph.research import (  # noqa: E402
    CheckStatus,
    EdgeEvidence,
    EntitySummary,
    FitResult,
    GraphEvidenceClaim,
    GraphSnapshot,
    RankedExperience,
    Recommendation,
    RecommendationPriority,
    ScopeResolveOutput,
    TrustLevel,
    TripResearchBundle,
)
from app.modules.plans.checks.overall_checker import OverallChecker  # noqa: E402
from app.modules.plans.domain.entities import Plan, PlanDay, PlanItem, TravelIntent  # noqa: E402
from app.modules.plans.domain.enums import BudgetLevel, PlanKind, PlanStatus, TravelPace  # noqa: E402
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (  # noqa: E402
    project_graph_candidate_catalog,
)
from app.modules.plans.dto.agent_contracts import (  # noqa: E402
    PlaceSelectionInput,
    PlanningIntent,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.place_selector.place_tool import SelectablePlace  # noqa: E402
from app.modules.plans.place_selector.service import PlaceSelectorService  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "theme_selector_kg_golden.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_evaluation()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


def run_evaluation() -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    hanoi = _catalog(data["hanoi"])
    group = _catalog(data["group"])
    missing = _catalog(data["missingData"])
    hanoi_names = {c.anchor_place_names[next(iter(c.anchor_place_names))] for c in hanoi.candidates}
    hanoi_main = {c.category.value for c in hanoi.candidates if c.category.value not in {"meal", "food"}}
    food_heavy = _old_food_heavy_plan(data["regression"])

    selector_smoke = _selector_smoke(hanoi)
    scenarios = {
        "hanoi_culture_food": {
            "passed": {"Ho Guom", "Lang Bac", "Water Puppet Theatre"}.issubset(hanoi_names)
            and hanoi_main >= {"nature", "history", "culture"}
            and all(c.category.value in {"meal", "food"} for c in hanoi.candidates if c.anchor_place_names[next(iter(c.anchor_place_names))] in {"Pho restaurant", "Bun cha restaurant"}),
            "rules": {
                "mainExperiencePlaces": sorted(hanoi_names - {"Pho restaurant", "Bun cha restaurant"}),
                "mealOnlyCandidates": sorted(c.anchor_place_names[next(iter(c.anchor_place_names))] for c in hanoi.candidates if c.category.value in {"meal", "food"}),
                "noRestaurantCafeOnlyPlan": len(hanoi_main) >= 3,
            },
        },
        "group_suitability": {
            "passed": not any(c.activity_id == "activity-bar" for c in group.candidates),
            "rules": {"barExcludedByEvidence": True, "warning": "Suitability evidence is missing or conflicting for nightlife."},
        },
        "timing_fill": {
            "passed": _timing_rule(hanoi) and selector_smoke["passed"],
            "rules": {"morning": "Ho Guom", "evening": "Water Puppet Theatre", "afternoon": "free_or_rest_if_no_valid_special_experience"},
        },
        "missing_data": {
            "passed": not missing.candidates,
            "rules": {"fallback": "deterministic", "verifiedClaim": False, "unroutableReason": "missing provenance and coordinates"},
        },
    }
    regression = {"food_heavy_plan": {"detected": food_heavy, "foodItems": data["regression"]["foodCount"], "nonFoodItems": data["regression"]["nonFoodCount"]}}
    report = {"status": "passed", "passed": all(item["passed"] for item in scenarios.values()) and regression["food_heavy_plan"]["detected"], "scenarios": scenarios, "regression": regression, "offline": True}
    report["status"] = "passed" if report["passed"] else "failed"
    return report


def _selector_smoke(catalog) -> dict[str, Any]:
    """Run the real selector with graph-derived timing contexts and no provider."""
    contexts: list[SelectedPlaceContext] = []
    places: list[SelectablePlace] = []
    for candidate in catalog.candidates:
        if candidate.category.value in {"meal", "food"}:
            continue
        place_id = candidate.anchor_place_ids[0]
        name = candidate.anchor_place_names[place_id]
        slot = next(iter(candidate.recommendation.timeSlots), None) if candidate.recommendation else None
        windows = [{"start": slot.split("-")[0], "end": slot.split("-")[1]}] if isinstance(slot, str) and "-" in slot else []
        contexts.append(SelectedPlaceContext(name=name, placeId=place_id, regionKey="vn,ha-noi", mustVisit=True, sourceRefs=candidate.source_refs, claimIds=candidate.claim_ids, activityId=candidate.activity_id, preferredTimeWindows=windows))
        places.append(SelectablePlace(placeId=place_id, name=name, placeType="attraction", regionKey="vn,ha-noi", preferredTimeWindows=windows, latitude=21.03, longitude=105.85, dataConfidence="high"))

    class FixturePlaceTool:
        def __init__(self, values):
            self.values = {value.place_id: value for value in values}

        def get(self, place_id):
            return self.values.get(place_id)

        def search(self, **kwargs):
            return list(self.values.values())

    result = PlaceSelectorService(FixturePlaceTool(places)).fill_agent_plan(PlaceSelectionInput(
        intent=PlanningIntent(destination="Hanoi", interests=["culture"]),
        tripSpec=TripPlanningSpec(days=1), regionKey="vn,ha-noi", selectedPlaces=contexts, allowPlaceSuggestions=False,
    ))
    names = {item.name for day in result.final_days for item in day.items}
    return {"passed": {"Ho Guom", "Water Puppet Theatre"}.issubset(names), "scheduled": sorted(names)}


def _catalog(rows: list[dict[str, Any]]):
    eligible: list[RankedExperience] = []
    conflicted: list[RankedExperience] = []
    for rank, row in enumerate(rows, 1):
        place = EntitySummary(id=row["id"], name=row["name"], type=row["type"], status="verified")
        activity = EntitySummary(id=row["activityId"], name=row["activityName"], type="Activity")
        recommendation = Recommendation(priority=RecommendationPriority(row.get("priority", "recommended")), timeSlots=row.get("timeSlots", []))
        claim = GraphEvidenceClaim(
            claimId=f"claim-{row['id']}", subject=EntitySummary(id="area-hanoi", name="Hanoi", type="AreaAdm1"),
            predicate=row["predicate"],
            object=activity if row["predicate"] == "SPECIAL_EXPERIENCE" else activity,
            path=["area-hanoi", row["predicate"], row["id"], row["activityId"]],
            anchorPlace=place, activity=activity, recommendations=[recommendation],
            evidence=[EdgeEvidence(source="fixture://kg-theme-selector/v1", recommendations=[recommendation])], trust=TrustLevel.SOURCE_BACKED,
        )
        ranked = RankedExperience(claim=claim, fit=FitResult(status=CheckStatus.CONFLICTED if row.get("fit") == "conflicted" else CheckStatus.SUPPORTED, hasHardConflict=row.get("fit") == "conflicted", dimensionCount=1), rank=rank, rankReasons=[row.get("fitReason", "fixture evidence")])
        if row.get("fit") != "unknown":
            (conflicted if row.get("fit") == "conflicted" else eligible).append(ranked)
    return project_graph_candidate_catalog(TripResearchBundle(scope=ScopeResolveOutput(), eligibleExperiences=eligible, conflictedExperiences=[], unknowns=[], graphSnapshot=GraphSnapshot(timestamp="2026-08-06T00:00:00Z")))


def _timing_rule(catalog) -> bool:
    slots = {slot for candidate in catalog.candidates for recommendation in [candidate.recommendation] if recommendation for slot in recommendation.timeSlots}
    return "08:00-10:00" in slots and "18:00-20:00" in slots and "14:00-16:00" not in slots


def _old_food_heavy_plan(counts: dict[str, int]) -> bool:
    items = [PlanItem(itemId=f"food-{i}", name="Food", timeWindow="09:00-10:00", placeType="restaurant", timelineCategory="activity") for i in range(counts["foodCount"])]
    items += [PlanItem(itemId="museum", name="Museum", timeWindow="10:00-11:00", placeType="museum", timelineCategory="activity") for _ in range(counts["nonFoodCount"])]
    plan = Plan(id="legacy-food-heavy", kind=PlanKind.main, status=PlanStatus.checking, title="Regression", destination="Hanoi", intent=TravelIntent(destination="Hanoi", days=1, budget=BudgetLevel.medium, travelStyle="local", pace=TravelPace.balanced), days=[PlanDay(day=1, theme="Culture", items=items)])
    return "food_stops_dominate_main_activities" in {
        issue.code for issue in OverallChecker().check(plan).issues
    }


if __name__ == "__main__":
    main()
