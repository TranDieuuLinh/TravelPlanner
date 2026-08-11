from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.modules.explorer.adapters.development import (
    InMemoryExplorerSnapshotRepository,
    InlineImageSourceExtractor,
    RuleBasedExplorerDraftGenerator,
    UnconfiguredUrlSourceExtractor,
)
from app.modules.explorer.nodes import ExplorerNodes
from app.modules.explorer.service import ExplorerService
from app.modules.explorer.state import ExplorerState


def route_intake(state: ExplorerState) -> Literal["prompt_only", "source_import"]:
    payload = state["payload"]
    return "source_import" if payload.urls or payload.images else "prompt_only"


def route_coverage(state: ExplorerState) -> Literal["synthesize", "failure"]:
    return "failure" if state["coverage"] == "fatal" else "synthesize"


def route_draft(state: ExplorerState) -> Literal["normalize", "failure"]:
    return "failure" if state.get("failure") else "normalize"


def route_completion(state: ExplorerState) -> Literal["ready", "clarification"]:
    return "ready" if state["output"].status == "ready" else "clarification"


def build_explorer_graph(service: ExplorerService | None = None):
    if service is None:
        drafts = RuleBasedExplorerDraftGenerator()
        service = ExplorerService(
            drafts, UnconfiguredUrlSourceExtractor(), InlineImageSourceExtractor(drafts),
            InMemoryExplorerSnapshotRepository(),
        )
    nodes = ExplorerNodes(service)
    builder = StateGraph(ExplorerState)
    for name in (
        "prepare_intake", "extract_prompt_structured_draft", "extract_sources",
        "evaluate_batch_coverage", "synthesize_explorer_draft", "normalize_and_validate",
        "reconcile_input_adm", "apply_defaults_and_precedence", "mark_failure",
        "persist_ready_snapshot", "persist_clarification_snapshot", "persist_failure_snapshot",
    ):
        builder.add_node(name, getattr(nodes, name))
    builder.add_edge(START, "prepare_intake")
    builder.add_conditional_edges("prepare_intake", route_intake, {
        "prompt_only": "extract_prompt_structured_draft", "source_import": "extract_sources"
    })
    builder.add_edge("extract_sources", "evaluate_batch_coverage")
    builder.add_conditional_edges("evaluate_batch_coverage", route_coverage, {
        "synthesize": "synthesize_explorer_draft", "failure": "mark_failure"
    })
    for source in ("extract_prompt_structured_draft", "synthesize_explorer_draft"):
        builder.add_conditional_edges(source, route_draft, {
            "normalize": "normalize_and_validate", "failure": "mark_failure"
        })
    builder.add_edge("normalize_and_validate", "reconcile_input_adm")
    builder.add_edge("reconcile_input_adm", "apply_defaults_and_precedence")
    builder.add_conditional_edges("apply_defaults_and_precedence", route_completion, {
        "ready": "persist_ready_snapshot", "clarification": "persist_clarification_snapshot"
    })
    builder.add_edge("mark_failure", "persist_failure_snapshot")
    for node in ("persist_ready_snapshot", "persist_clarification_snapshot", "persist_failure_snapshot"):
        builder.add_edge(node, END)
    return builder.compile()
