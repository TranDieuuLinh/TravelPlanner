from typing import Protocol

from app.modules.information_finder.contract import InformationFinderOutput


class InformationProvider(Protocol):
    async def search(self, query: str) -> InformationFinderOutput: ...


class UnconfiguredInformationProvider:
    async def search(self, query: str) -> InformationFinderOutput:
        return InformationFinderOutput(
            answer=(
                "Information provider is not configured yet. "
                f"The validated query was: {query}"
            )
        )

