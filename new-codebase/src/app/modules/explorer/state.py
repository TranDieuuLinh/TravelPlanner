from typing import TypedDict

from app.modules.explorer.contract import ExplorerOutput
from app.shared.contracts.place import PlaceCandidate


class ExplorerState(TypedDict, total=False):
    message: str
    supplied_candidates: list[PlaceCandidate]
    output: ExplorerOutput

