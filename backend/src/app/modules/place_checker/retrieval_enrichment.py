from app.modules.place_checker.ports import PlaceMetadataRepository
from app.modules.place_checker.retrieval_contract import RetrievedCandidate


class RetrievalMetadataEnricher:
    def __init__(
        self,
        repository: PlaceMetadataRepository | None,
    ) -> None:
        self.repository = repository

    async def enrich(
        self,
        candidates: list[RetrievedCandidate],
    ) -> tuple[list[RetrievedCandidate], list[str]]:
        place_ids = [
            candidate.place_id
            for candidate in candidates
            if candidate.place_id is not None
        ]
        if self.repository is None or not place_ids:
            return candidates, []
        try:
            metadata_by_id = await self.repository.get_many(place_ids)
        except Exception:
            return candidates, ["Không thể làm giàu metadata cho candidate mới."]
        enriched: list[RetrievedCandidate] = []
        for candidate in candidates:
            metadata = metadata_by_id.get(candidate.place_id or "")
            if metadata is None:
                enriched.append(candidate)
                continue
            enriched.append(
                candidate.model_copy(
                    update={
                        "metadata": metadata,
                        "coordinates": metadata.coordinates or candidate.coordinates,
                        "category": metadata.category or candidate.category,
                        "tags": list(dict.fromkeys([*candidate.tags, *metadata.tags])),
                    }
                )
            )
        return enriched, []
