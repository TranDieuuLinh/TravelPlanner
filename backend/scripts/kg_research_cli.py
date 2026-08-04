#!/usr/bin/env python3
"""CLI for Knowledge Graph research operations.

Usage:
    python scripts/kg_research_cli.py stats
    python scripts/kg_research_cli.py resolve-scope --destination "Hà Nội" --pretty
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
    ScopeResolveInput,
    ScopeResolveOutput,
    ScopeResolutionRepository,
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
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
