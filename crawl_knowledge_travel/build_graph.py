from __future__ import annotations

import argparse
import json
from pathlib import Path

from travel_crawl.knowledge_graph import (
    build_operational_graph,
    load_normalized_records,
    write_graph,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_GRAPH = (
    ROOT.parent
    / "backend"
    / "app"
    / "modules"
    / "plans"
    / "knowledge_graph"
    / "hanoi_graph.v1.json"
)
DEFAULT_OUTPUT = DEFAULT_BASE_GRAPH.with_name("hanoi_graph.v2.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Planner/Finder operational graph from normalized sources."
    )
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data" / "normalized")
    parser.add_argument("--base-graph", type=Path, default=DEFAULT_BASE_GRAPH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-evidence-per-node", type=int, default=8)
    args = parser.parse_args()

    records = load_normalized_records(args.input_dir)
    base_graph = json.loads(args.base_graph.read_text(encoding="utf-8"))
    graph = build_operational_graph(
        base_graph,
        records,
        max_evidence_per_node=args.max_evidence_per_node,
    )
    write_graph(args.output, graph)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "schemaVersion": graph["schemaVersion"],
                **graph["build"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
