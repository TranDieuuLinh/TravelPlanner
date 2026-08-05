#!/usr/bin/env python3
"""CLI for Knowledge Graph research operations.

Usage:
    python scripts/kg_research_cli.py stats
    python scripts/kg_research_cli.py resolve-scope --destination "Hà Nội" --pretty
    python scripts/kg_research_cli.py evaluate-fit --entity-id "..." --destination "Hà Nội" --days 3 --pretty
    python scripts/kg_research_cli.py discover-experiences --destination "Hà Nội" --pretty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.knowledge_graph.research import (
    BudgetLevel,
    ExperienceDiscoveryInput,
    ExperienceFitInput,
    ExperienceFitOutput,
    GraphEvidenceBundle,
    GraphSnapshot,
    GraphResearchOrchestrator,
    GraphScopeError,
    ScopeResolveInput,
    ScopeResolveOutput,
    ScopeResolutionRepository,
    TransportMode,
    TravelBudget,
    TripResearchBundle,
    TripResearchInput,
    kg_discover_experiences,
    kg_evaluate_experience_fit,
    kg_resolve_scope,
)


def cmd_stats(db_url: str) -> int:
    """Display knowledge graph statistics."""
    print(f"# Knowledge Graph Statistics", file=sys.stderr)
    print(f"# Database: postgresql+psycopg://***", file=sys.stderr)
    print(file=sys.stderr)

    session = SessionLocal()
    try:
        repo = ScopeResolutionRepository(session)
        stats = repo.stats()

        output = {
            "entityCount": stats.entityCount,
            "aliasCount": stats.aliasCount,
            "relationshipCount": stats.relationshipCount,
            "areaCount": stats.areaCount,
            "areaAdm0Count": stats.areaAdm0Count,
            "areaAdm1Count": stats.areaAdm1Count,
            "areaAdm2Count": stats.areaAdm2Count,
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_resolve_scope(
    destination: str,
    place_ids: list[str] | None,
    max_depth: int,
    result_limit: int,
    pretty: bool,
) -> int:
    """Resolve geographic scope for a destination."""
    print(f"# Resolve Scope: {destination}", file=sys.stderr)
    print(f"# Database: postgresql+psycopg://***", file=sys.stderr)
    if place_ids:
        print(f"# Selected Place IDs: {len(place_ids)}", file=sys.stderr)
    print(file=sys.stderr)

    session = SessionLocal()
    try:
        repo = ScopeResolutionRepository(session)

        if repo.is_empty():
            output = ScopeResolveOutput(
                rootArea=None,
                ancestors=[],
                includedAreas=[],
                selectedPlaceAreas=[],
                warnings=["KNOWLEDGE_GRAPH_EMPTY: Graph has no entities. Import data first."],
            )
            print(output.model_dump_json(by_alias=True, indent=2 if pretty else None), file=sys.stdout)
            print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
            return 1

        input_data = ScopeResolveInput(
            destination=destination,
            selectedPlaceIds=place_ids,
            maxDepth=max_depth,
            resultLimit=result_limit,
        )

        result = kg_resolve_scope(repo, input_data)

        indent = 2 if pretty else None
        print(result.model_dump_json(by_alias=True, indent=indent), file=sys.stdout)

        for warning in result.warnings:
            if "KNOWLEDGE_GRAPH_EMPTY" in warning:
                print(warning.split(":")[0], file=sys.stderr)
                return 1

        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_evaluate_fit(
    entity_id: str | None,
    claim_id: str | None,
    destination: str,
    days: int,
    party_size: int,
    start_date: str | None,
    end_date: str | None,
    budget_level: str | None,
    budget_target: float | None,
    excluded_types: list[str],
    preferred_transport: list[str],
    avoided_transport: list[str],
    accessibility: list[str],
    constraints: list[str],
    pretty: bool,
) -> int:
    """Evaluate experience fit for an entity."""
    target = entity_id or claim_id or "(not specified)"
    print(f"# Evaluate Fit: {target}", file=sys.stderr)
    print(f"# Destination: {destination} | Days: {days} | Party: {party_size}", file=sys.stderr)
    print(f"# Database: postgresql+psycopg://***", file=sys.stderr)
    print(file=sys.stderr)

    session = SessionLocal()
    try:
        repo = ScopeResolutionRepository(session)

        if repo.is_empty():
            output = ExperienceFitOutput(
                entity=None,
                overallStatus="unknown",
                checks=[],
                warnings=["KNOWLEDGE_GRAPH_EMPTY: Graph has no entities. Import data first."],
            )
            print(output.model_dump_json(by_alias=True, indent=2 if pretty else None), file=sys.stdout)
            print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
            return 1

        parsed_budget: BudgetLevel | None = None
        if budget_level is not None:
            try:
                parsed_budget = BudgetLevel(budget_level.lower())
            except ValueError:
                print(json.dumps({"error": f"Invalid budget level: {budget_level}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        parsed_preferred: list[TransportMode] = []
        for t in preferred_transport:
            try:
                parsed_preferred.append(TransportMode(t.lower()))
            except ValueError:
                print(json.dumps({"error": f"Invalid transport mode: {t}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        parsed_avoided: list[TransportMode] = []
        for t in avoided_transport:
            try:
                parsed_avoided.append(TransportMode(t.lower()))
            except ValueError:
                print(json.dumps({"error": f"Invalid transport mode: {t}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        input_data = ExperienceFitInput(
            entityId=entity_id,
            claimId=claim_id,
            destination=destination,
            days=days,
            partySize=party_size,
            startDate=start_date,
            endDate=end_date,
            budgetLevel=parsed_budget,
            budgetTargetAmount=budget_target,
            excludedPlaceTypes=excluded_types,
            preferredTransportModes=parsed_preferred,
            avoidedTransportModes=parsed_avoided,
            accessibilityRequirements=accessibility,
            userConstraints=constraints,
        )

        result = kg_evaluate_experience_fit(repo, input_data)

        indent = 2 if pretty else None
        print(result.model_dump_json(by_alias=True, indent=indent), file=sys.stdout)

        for warning in result.warnings:
            if "KNOWLEDGE_GRAPH_EMPTY" in warning:
                print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
                return 1

        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_discover_experiences(
    destination: str | None,
    root_area_id: str | None,
    interests: list[str] | None,
    selected_place_ids: list[str] | None,
    limit: int,
    include_inferred: bool,
    pretty: bool,
) -> int:
    """Discover special experiences for a destination."""
    dest_arg = destination or root_area_id or "unknown"
    print(f"# Discover Experiences: {dest_arg}", file=sys.stderr)
    print(f"# Database: postgresql+psycopg://***", file=sys.stderr)
    if interests:
        print(f"# Interests: {', '.join(interests)}", file=sys.stderr)
    print(file=sys.stderr)

    session = SessionLocal()
    try:
        repo = ScopeResolutionRepository(session)

        if repo.is_empty():
            output = GraphEvidenceBundle(
                claims=[],
                unknowns=[],
                warnings=["KNOWLEDGE_GRAPH_EMPTY: Graph has no entities. Import data first."],
                graphSnapshot=GraphSnapshot(timestamp=""),
            )
            print(output.model_dump_json(by_alias=True, indent=2 if pretty else None), file=sys.stdout)
            print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
            return 1

        input_data = ExperienceDiscoveryInput(
            destination=destination,
            rootAreaId=root_area_id,
            interests=interests or [],
            selectedPlaceIds=selected_place_ids,
            limit=limit,
            includeInferred=include_inferred,
        )

        result = kg_discover_experiences(repo, input_data)

        indent = 2 if pretty else None
        print(result.model_dump_json(by_alias=True, indent=indent), file=sys.stdout)

        for warning in result.warnings:
            if "KNOWLEDGE_GRAPH_EMPTY" in warning:
                print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
                return 1
            if "DESTINATION_NOT_FOUND" in warning:
                print("DESTINATION_NOT_FOUND", file=sys.stderr)
                return 1

        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_research_trip(
    destination: str,
    interests: list[str] | None,
    selected_place_ids: list[str] | None,
    days: int,
    party_size: int,
    start_date: str | None,
    end_date: str | None,
    budget_level: str | None,
    budget_amount: float | None,
    excluded_types: list[str],
    preferred_modes: list[str],
    avoid_modes: list[str],
    exclude_inferred: bool,
    limit: int,
    pretty: bool,
) -> int:
    """Run full trip research orchestration."""
    print(f"# Research Trip: {destination}", file=sys.stderr)
    print(f"# Database: postgresql+psycopg://***", file=sys.stderr)
    print(f"# Days: {days} | Party: {party_size}", file=sys.stderr)
    if interests:
        print(f"# Interests: {', '.join(interests)}", file=sys.stderr)
    print(file=sys.stderr)

    session = SessionLocal()
    try:
        repo = ScopeResolutionRepository(session)

        if repo.is_empty():
            print(json.dumps({
                "error": "KNOWLEDGE_GRAPH_EMPTY",
                "message": "Graph has no entities. Import data first.",
            }, ensure_ascii=False), file=sys.stderr)
            print("KNOWLEDGE_GRAPH_EMPTY", file=sys.stderr)
            return 1

        # Parse budget level
        parsed_budget_level: BudgetLevel = BudgetLevel.MEDIUM
        if budget_level is not None:
            try:
                parsed_budget_level = BudgetLevel(budget_level.lower())
            except ValueError:
                print(json.dumps({"error": f"Invalid budget level: {budget_level}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        # Parse transport modes
        parsed_preferred: list[TransportMode] = []
        for mode in preferred_modes:
            try:
                parsed_preferred.append(TransportMode(mode.lower()))
            except ValueError:
                print(json.dumps({"error": f"Invalid transport mode: {mode}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        parsed_avoid: list[TransportMode] = []
        for mode in avoid_modes:
            try:
                parsed_avoid.append(TransportMode(mode.lower()))
            except ValueError:
                print(json.dumps({"error": f"Invalid transport mode: {mode}"}, ensure_ascii=False), file=sys.stderr)
                return 1

        # Build input
        input_data = TripResearchInput(
            destination=destination,
            selectedPlaceIds=selected_place_ids or [],
            interests=interests or [],
            days=days,
            partySize=party_size,
            startDate=start_date,
            endDate=end_date,
            budget=TravelBudget(
                level=parsed_budget_level,
                targetAmount=budget_amount,
                currency="VND",
            ),
            excludedPlaceTypes=excluded_types,
            preferredModes=parsed_preferred,
            avoidModes=parsed_avoid,
            includeInferred=not exclude_inferred,
            candidateLimit=limit,
        )

        # Run orchestration
        orchestrator = GraphResearchOrchestrator(repo, repo)
        result = orchestrator.research(input_data)

        indent = 2 if pretty else None
        print(result.model_dump_json(by_alias=True, indent=indent), file=sys.stdout)

        # Check for scope error
        for warning in result.warnings:
            if "GRAPH_SCOPE_NOT_FOUND" in warning:
                print("GRAPH_SCOPE_NOT_FOUND", file=sys.stderr)
                return 1
            if "GRAPH_EXPERIENCE_COVERAGE_EMPTY" in warning:
                print("GRAPH_EXPERIENCE_COVERAGE_EMPTY", file=sys.stderr)
                return 0

        return 0
    except GraphScopeError as e:
        print(json.dumps({"error": e.CODE, "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        print(e.CODE, file=sys.stderr)
        return 1
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="kg_research_cli",
        description="Knowledge Graph research CLI tools",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Show knowledge graph statistics",
    )

    resolve_parser = subparsers.add_parser(
        "resolve-scope",
        help="Resolve geographic scope for a destination",
    )
    resolve_parser.add_argument(
        "--destination",
        required=True,
        help="Destination name to resolve",
    )
    resolve_parser.add_argument(
        "--place-ids",
        nargs="+",
        help="Optional Place entity IDs to map to Areas",
    )
    resolve_parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum PART_OF traversal depth (default: 4)",
    )
    resolve_parser.add_argument(
        "--result-limit",
        type=int,
        default=100,
        help="Maximum number of areas to return (default: 100)",
    )
    resolve_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    fit_parser = subparsers.add_parser(
        "evaluate-fit",
        help="Evaluate whether an entity fits a user's trip context",
    )
    fit_parser.add_argument(
        "--entity-id",
        help="Entity ID to evaluate (mutually exclusive with --claim-id)",
    )
    fit_parser.add_argument(
        "--claim-id",
        help="Claim/Experience ID to evaluate (mutually exclusive with --entity-id)",
    )
    fit_parser.add_argument(
        "--destination",
        required=True,
        help="Destination name for scope check",
    )
    fit_parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Number of trip days (1-30)",
    )
    fit_parser.add_argument(
        "--party-size",
        type=int,
        default=1,
        help="Number of travelers (default: 1)",
    )
    fit_parser.add_argument(
        "--start-date",
        help="Trip start date (ISO 8601)",
    )
    fit_parser.add_argument(
        "--end-date",
        help="Trip end date (ISO 8601)",
    )
    fit_parser.add_argument(
        "--budget-level",
        choices=["low", "medium", "high", "luxury"],
        help="Budget level preference",
    )
    fit_parser.add_argument(
        "--budget-target",
        type=float,
        help="Target total budget in VND",
    )
    fit_parser.add_argument(
        "--exclude-type",
        nargs="+",
        default=[],
        dest="excluded_types",
        help="Place types to exclude (e.g. Restaurant Accommodation)",
    )
    fit_parser.add_argument(
        "--preferred-transport",
        nargs="+",
        default=[],
        dest="preferred_transport",
        help="Preferred transport modes (walking cycling public_transit taxi car boat motorbike)",
    )
    fit_parser.add_argument(
        "--avoided-transport",
        nargs="+",
        default=[],
        dest="avoided_transport",
        help="Transport modes to avoid",
    )
    fit_parser.add_argument(
        "--accessibility",
        nargs="+",
        default=[],
        help="Accessibility requirements (e.g. wheelchair hearing_aid)",
    )
    fit_parser.add_argument(
        "--constraint",
        nargs="+",
        default=[],
        dest="constraints",
        help="Additional user-defined constraints",
    )
    fit_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    discover_parser = subparsers.add_parser(
        "discover-experiences",
        help="Discover special experiences in a destination",
    )
    discover_parser.add_argument(
        "--destination",
        help="Destination name to resolve",
    )
    discover_parser.add_argument(
        "--root-area-id",
        help="Root Area entity ID (alternative to destination)",
    )
    discover_parser.add_argument(
        "--interest",
        action="append",
        dest="interests",
        help="Interest tag to filter by (can be specified multiple times)",
    )
    discover_parser.add_argument(
        "--place-ids",
        nargs="+",
        dest="place_ids",
        help="Optional Place entity IDs to filter by",
    )
    discover_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of claims to return (default: 20, max: 50)",
    )
    discover_parser.add_argument(
        "--no-inferred",
        action="store_false",
        dest="include_inferred",
        help="Exclude inferred claims (default: include inferred)",
    )
    discover_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    research_parser = subparsers.add_parser(
        "research-trip",
        help="Run full trip research orchestration",
    )
    research_parser.add_argument(
        "--destination",
        required=True,
        help="Destination name to research",
    )
    research_parser.add_argument(
        "--interest",
        action="append",
        dest="interests",
        help="Interest tag (can be specified multiple times)",
    )
    research_parser.add_argument(
        "--selected-place-id",
        action="append",
        dest="selected_place_ids",
        help="Pre-selected Place entity ID (can be specified multiple times)",
    )
    research_parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of trip days (default: 3)",
    )
    research_parser.add_argument(
        "--party-size",
        type=int,
        default=2,
        dest="party_size",
        help="Number of travelers (default: 2)",
    )
    research_parser.add_argument(
        "--start-date",
        dest="start_date",
        help="Trip start date (ISO 8601)",
    )
    research_parser.add_argument(
        "--end-date",
        dest="end_date",
        help="Trip end date (ISO 8601)",
    )
    research_parser.add_argument(
        "--budget-level",
        choices=["low", "medium", "high", "luxury"],
        dest="budget_level",
        help="Budget level preference",
    )
    research_parser.add_argument(
        "--budget-amount",
        type=float,
        dest="budget_amount",
        help="Target total budget in VND",
    )
    research_parser.add_argument(
        "--exclude-place-type",
        action="append",
        dest="excluded_types",
        help="Place type to exclude (can be specified multiple times)",
    )
    research_parser.add_argument(
        "--preferred-mode",
        action="append",
        dest="preferred_modes",
        help="Preferred transport mode (can be specified multiple times)",
    )
    research_parser.add_argument(
        "--avoid-mode",
        action="append",
        dest="avoid_modes",
        help="Transport mode to avoid (can be specified multiple times)",
    )
    research_parser.add_argument(
        "--exclude-inferred",
        action="store_true",
        dest="exclude_inferred",
        help="Exclude inferred claims",
    )
    research_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum candidates to return (default: 30, max: 100)",
    )
    research_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    args = parser.parse_args()

    if args.command == "stats":
        return cmd_stats(settings.database_url)
    elif args.command == "resolve-scope":
        return cmd_resolve_scope(
            destination=args.destination,
            place_ids=args.place_ids,
            max_depth=args.max_depth,
            result_limit=args.result_limit,
            pretty=args.pretty,
        )
    elif args.command == "evaluate-fit":
        return cmd_evaluate_fit(
            entity_id=args.entity_id,
            claim_id=args.claim_id,
            destination=args.destination,
            days=args.days,
            party_size=args.party_size,
            start_date=args.start_date,
            end_date=args.end_date,
            budget_level=args.budget_level,
            budget_target=args.budget_target,
            excluded_types=args.excluded_types,
            preferred_transport=args.preferred_transport,
            avoided_transport=args.avoided_transport,
            accessibility=args.accessibility,
            constraints=args.constraints,
            pretty=args.pretty,
        )
    elif args.command == "discover-experiences":
        return cmd_discover_experiences(
            destination=args.destination,
            root_area_id=args.root_area_id,
            interests=args.interests,
            selected_place_ids=args.place_ids,
            limit=args.limit,
            include_inferred=args.include_inferred,
            pretty=args.pretty,
        )
    elif args.command == "research-trip":
        return cmd_research_trip(
            destination=args.destination,
            interests=args.interests,
            selected_place_ids=args.selected_place_ids,
            days=args.days,
            party_size=args.party_size,
            start_date=args.start_date,
            end_date=args.end_date,
            budget_level=args.budget_level,
            budget_amount=args.budget_amount,
            excluded_types=args.excluded_types or [],
            preferred_modes=args.preferred_modes or [],
            avoid_modes=args.avoid_modes or [],
            exclude_inferred=args.exclude_inferred,
            limit=args.limit,
            pretty=args.pretty,
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
