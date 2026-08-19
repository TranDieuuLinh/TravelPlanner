from app.modules.information_finder.contract import RetrievedSource

SEMANTIC_WEIGHT = 0.65
LEXICAL_WEIGHT = 0.25
FRESHNESS_WEIGHT = 0.10


def rank_sources(sources: list[RetrievedSource]) -> list[RetrievedSource]:
    def score(source: RetrievedSource) -> float:
        return (
            SEMANTIC_WEIGHT * source.semantic_score
            + LEXICAL_WEIGHT * source.lexical_score
            + FRESHNESS_WEIGHT * source.freshness_score
        )

    best_by_url: dict[str, RetrievedSource] = {}
    for source in sources:
        current = best_by_url.get(source.url)
        if current is None or score(source) > score(current):
            best_by_url[source.url] = source
    return sorted(best_by_url.values(), key=score, reverse=True)
