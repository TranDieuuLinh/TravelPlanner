from typing import TypedDict

from app.modules.information_finder.contract import InformationFinderOutput


class InformationFinderState(TypedDict, total=False):
    query: str
    output: InformationFinderOutput
