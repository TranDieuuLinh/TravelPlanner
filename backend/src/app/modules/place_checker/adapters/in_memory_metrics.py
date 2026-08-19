class InMemoryPlaceCheckerMetrics:
    def __init__(self) -> None:
        self.records: list[tuple[str, float, dict[str, str]]] = []

    async def record(
        self,
        metric: str,
        value: float,
        tags: dict[str, str],
    ) -> None:
        self.records.append((metric, value, tags))
