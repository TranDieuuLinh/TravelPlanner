from typing import TypedDict

from app.modules.explorer.public import ExplorerBudget, ExplorerPeople, ExplorerPlace, RequestedItem, SourceNote
from app.modules.place_checker.contract import PlaceCheckerOutput


class PlaceCheckerState(TypedDict, total=False):
    input_adm: str
    places: list[ExplorerPlace] | None
    input_items: list[RequestedItem] | None
    url_notes: list[SourceNote] | None
    days: int
    budget: ExplorerBudget
    people: ExplorerPeople
    short_preferences: list[str]
    short_avoids: list[str]
    output: PlaceCheckerOutput
