from app.modules.information_finder.contract import InformationFinderOutput
from app.modules.information_finder.ports import InformationProvider


class InformationFinderService:
    def __init__(self, provider: InformationProvider) -> None:
        self.provider = provider

    async def find(self, query: str) -> InformationFinderOutput:
        return await self.provider.search(query)

