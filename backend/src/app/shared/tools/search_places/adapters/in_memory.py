from app.shared.tools.search_places.contract import (
    AdministrativeArea,
    PlaceProviderCandidate,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.ports import PlaceSearchProviderError


class InMemoryPlaceSearch:
    """Deterministic test/development adapter; it never invents place data."""

    def __init__(
        self,
        candidates: list[PlaceProviderCandidate] | None = None,
        *,
        provider_name: str = "in_memory",
        error: PlaceSearchProviderError | None = None,
    ) -> None:
        self.candidates = candidates or []
        self.provider_name = provider_name
        self.error = error
        self.calls: list[list[str]] = []

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
    ) -> list[PlaceProviderCandidate]:
        self.calls.append(lookup_names)
        if self.error is not None:
            raise self.error
        terms = {normalize_text(name) for name in lookup_names}
        ranked = sorted(
            self.candidates,
            key=lambda candidate: (
                not any(
                    term in {
                        normalize_text(candidate.name),
                        *(normalize_text(alias) for alias in candidate.aliases),
                        *(normalize_text(tag) for tag in candidate.tags),
                    }
                    for term in terms
                ),
                -candidate.data_confidence,
            ),
        )
        return ranked[:limit]

