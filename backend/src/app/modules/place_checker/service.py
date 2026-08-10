from app.modules.place_checker.contract import PlaceCheckerInput, PlaceCheckerOutput
from app.modules.place_checker.ports import PlaceDiscovery, PlaceResolver
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace


class PlaceCheckerService:
    def __init__(self, resolver: PlaceResolver, discovery: PlaceDiscovery) -> None:
        self.resolver = resolver
        self.discovery = discovery

    @staticmethod
    def required_count(days: int) -> int:
        return max(2, days * 2)

    async def check(self, payload: PlaceCheckerInput) -> PlaceCheckerOutput:
        resolved: list[VerifiedPlace] = []
        rejected: list[PlaceCandidate] = []
        seen: set[str] = set()

        for candidate in payload.candidates:
            place = await self.resolver.resolve(candidate, payload.intent)
            if place is None:
                rejected.append(candidate)
                continue
            identity = place.place_id.casefold()
            if identity not in seen:
                seen.add(identity)
                resolved.append(place)

        required = self.required_count(payload.intent.days)
        if len(resolved) < required:
            discovered = await self.discovery.discover(
                payload.intent,
                required - len(resolved),
            )
            for place in discovered:
                if place.place_id.casefold() not in seen:
                    seen.add(place.place_id.casefold())
                    resolved.append(place)

        unverified_count = sum(not place.verified for place in resolved)
        warnings = []
        if unverified_count:
            warnings.append(
                f"{unverified_count} place(s) require verification by a real provider."
            )
        status = "sufficient" if len(resolved) >= required else "insufficient"
        return PlaceCheckerOutput(
            places=resolved,
            rejected_candidates=rejected,
            coverage_status=status,
            warnings=warnings,
        )

