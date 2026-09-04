from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetRangeResult:
    region: str
    category: str | None
    currency: str
    q1: float | None
    median: float | None
    q3: float | None
    sample_count: int
    warnings: tuple[str, ...] = ()


class BudgetRangeTool:
    """Calculate budget suggestions from normalized Knowledge Graph prices."""

    def __init__(self, knowledge_graph) -> None:
        self.knowledge_graph = knowledge_graph

    async def search(
        self, region: str, *, category: str | None = None, currency: str = "VND"
    ) -> BudgetRangeResult:
        observations = await self.knowledge_graph.get_price_observations(
            region, category, currency
        )
        values = sorted(
            float(item["value"])
            for item in observations
            if float(item.get("value", 0)) >= 0
        )
        warnings: list[str] = []
        if len(values) < 4:
            warnings.append("insufficient_price_samples")
        return BudgetRangeResult(
            region=region,
            category=category,
            currency=currency.upper(),
            q1=_percentile(values, 0.25),
            median=_percentile(values, 0.50),
            q3=_percentile(values, 0.75),
            sample_count=len(values),
            warnings=tuple(warnings),
        )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight
