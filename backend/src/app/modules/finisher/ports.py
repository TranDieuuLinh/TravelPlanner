from typing import Protocol

from app.modules.finisher.contract import FinisherInput, FinisherOutput


class FinisherResponseGenerator(Protocol):
    async def generate(self, payload: FinisherInput) -> FinisherOutput:
        """Create a concise Vietnamese response from normalized itinerary data."""
