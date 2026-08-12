import ast
from pathlib import Path

from app.modules.explorer.public import build_explorer_graph


MODULE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(__file__).resolve().parents[3]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
        elif isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
    return values


def test_graph_and_nodes_do_not_compose_adapters() -> None:
    for name in ("graph.py", "nodes.py"):
        imports = imported_modules(MODULE_ROOT / name)
        assert not any(".adapters" in value for value in imports)


def test_adapters_do_not_depend_on_langgraph_layers() -> None:
    forbidden = (".graph", ".nodes", ".service", ".state")
    for path in (MODULE_ROOT / "adapters").glob("*.py"):
        imports = imported_modules(path)
        assert not any(
            value.startswith("app.modules.explorer")
            and value.endswith(forbidden)
            for value in imports
        ), path.name


def test_other_app_modules_use_only_explorer_public_contract() -> None:
    violations = []
    for path in APP_ROOT.rglob("*.py"):
        if MODULE_ROOT in path.parents:
            continue
        for value in imported_modules(path):
            if value.startswith("app.modules.explorer.") and value != (
                "app.modules.explorer.public"
            ):
                violations.append((str(path.relative_to(APP_ROOT)), value))
    assert violations == []


def test_compiled_graph_has_expected_workflow_nodes() -> None:
    graph = build_explorer_graph()
    expected = {
        "prepare_intake",
        "extract_prompt_structured_draft",
        "extract_sources",
        "evaluate_batch_coverage",
        "synthesize_explorer_draft",
        "normalize_and_validate",
        "reconcile_input_adm",
        "apply_defaults_and_precedence",
        "mark_failure",
        "persist_ready_snapshot",
        "persist_clarification_snapshot",
        "persist_failure_snapshot",
    }
    assert expected <= set(graph.get_graph().nodes)
