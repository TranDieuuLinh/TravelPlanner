from types import SimpleNamespace

from app.orchestration.routes import explorer_can_plan, route_after_explorer


def output(status: str, destination: str | None):
    return SimpleNamespace(status=status, input_adm=destination)


def test_partial_source_import_with_destination_continues_to_place_checker() -> None:
    explorer = output("partial", "Hanoi")

    assert explorer_can_plan(explorer)
    assert route_after_explorer({"explorer_output": explorer}) == "place_checker"


def test_partial_source_import_without_destination_still_finishes() -> None:
    explorer = output("partial", None)

    assert not explorer_can_plan(explorer)
    assert route_after_explorer({"explorer_output": explorer}) == "finish"
