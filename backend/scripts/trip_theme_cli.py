#!/usr/bin/env python3
"""Inspect TripTheme-to-graph research context without invoking an LLM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.modules.knowledge_graph.research import (
    GraphResearchOrchestrator,
    ScopeResolutionRepository,
)
from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import (
    PlanningIntent,
    TripPlanningSpec,
    TransportMode,
)
from app.modules.plans.trip_theme_planner.graph_research import (
    TripThemeGraphResearchService,
)
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    project_graph_candidate_catalog,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trip_theme_cli",
        description="Inspect TripTheme graph research context without LLM calls.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    research_parser = subparsers.add_parser(
        "research-context",
        help="Build TripResearchInput and run the graph orchestrator.",
    )
    research_parser.add_argument("--destination", required=True)
    research_parser.add_argument("--destination-stay", action="append", default=[])
    research_parser.add_argument("--selected-place-id", action="append", default=[])
    research_parser.add_argument("--interest", action="append", default=[])
    research_parser.add_argument("--travel-style", default="local")
    research_parser.add_argument(
        "--pace",
        choices=[pace.value for pace in TravelPace],
        default=TravelPace.balanced.value,
    )
    research_parser.add_argument("--days", type=int, default=3)
    research_parser.add_argument("--party-size", type=int, default=1)
    research_parser.add_argument("--start-date")
    research_parser.add_argument("--end-date")
    research_parser.add_argument(
        "--budget-level",
        choices=["low", "medium", "high"],
        default="medium",
    )
    research_parser.add_argument("--budget-target", type=int)
    research_parser.add_argument("--currency", default="VND")
    research_parser.add_argument("--constraint", action="append", default=[])
    research_parser.add_argument(
        "--exclude-place-type",
        action="append",
        default=[],
    )
    research_parser.add_argument(
        "--preferred-mode",
        action="append",
        choices=[mode.value for mode in TransportMode],
        default=[],
    )
    research_parser.add_argument(
        "--avoid-mode",
        action="append",
        choices=[mode.value for mode in TransportMode],
        default=[],
    )
    research_parser.add_argument("--pretty", action="store_true")
    return parser


def research_context(args: argparse.Namespace) -> int:
    intent = PlanningIntent(
        destination=args.destination,
        travelStyle=args.travel_style,
        pace=args.pace,
        interests=args.interest,
        destinationStays=[
            {
                "name": name,
                "durationDays": 1,
                "startDay": index,
                "endDay": index,
            }
            for index, name in enumerate(args.destination_stay, start=1)
        ],
        constraints=args.constraint,
        constraintPolicy=ConstraintPolicy(
            excludedPlaceTypes=args.exclude_place_type,
        ),
    )
    trip_spec = TripPlanningSpec(
        days=args.days,
        partySize=args.party_size,
        startDate=args.start_date,
        endDate=args.end_date,
        budget={
            "level": args.budget_level,
            "targetAmount": args.budget_target,
            "currency": args.currency,
        },
        transport={
            "preferredModes": args.preferred_mode,
            "avoidModes": args.avoid_mode,
        },
    )

    session = SessionLocal()
    try:
        repository = ScopeResolutionRepository(session)
        orchestrator = GraphResearchOrchestrator(repository, repository)
        service = TripThemeGraphResearchService(orchestrator)
        result = service.research(
            intent,
            trip_spec,
            args.selected_place_id,
        )
        research_input = service_input(
            intent,
            trip_spec,
            args.selected_place_id,
        )
        output = {
            "researchInput": research_input.model_dump(mode="json", by_alias=True),
            "researchBundle": result.model_dump(mode="json", by_alias=True),
            "graphCandidateCatalog": project_graph_candidate_catalog(result).model_dump(
                mode="json",
                by_alias=True,
            ),
        }
        print(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps({"error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()


def service_input(intent, trip_spec, selected_place_ids):
    """Build the same bounded input used by the service for CLI display."""
    from app.modules.plans.trip_theme_planner.graph_research import (
        build_trip_research_input,
    )

    return build_trip_research_input(intent, trip_spec, selected_place_ids)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "research-context":
        return research_context(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
