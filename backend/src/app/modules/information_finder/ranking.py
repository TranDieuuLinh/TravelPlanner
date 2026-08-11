import re
import unicodedata

from app.modules.information_finder.contract import RetrievedSource

SEMANTIC_WEIGHT = 0.65
LEXICAL_WEIGHT = 0.25
FRESHNESS_WEIGHT = 0.10
_TOPIC_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "can",
        "cho",
        "do",
        "does",
        "for",
        "gì",
        "how",
        "is",
        "là",
        "me",
        "more",
        "mình",
        "muốn",
        "này",
        "of",
        "please",
        "the",
        "thêm",
        "thông",
        "tin",
        "tôi",
        "to",
        "về",
        "what",
        "you",
    }
)


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


def has_sufficient_local_sources(
    sources: list[RetrievedSource],
    *,
    query: str = "",
    minimum_sources: int,
    similarity_threshold: float,
    minimum_content_chars: int,
    topic_overlap_threshold: float = 0.75,
) -> bool:
    qualified = [
        source
        for source in sources
        if source.semantic_score >= similarity_threshold
        and len(source.content.strip()) >= minimum_content_chars
    ]
    topic_terms = _topic_terms(query)
    if len(topic_terms) >= 2:
        qualified = [
            source
            for source in qualified
            if _topic_overlap(source.content, topic_terms) >= topic_overlap_threshold
        ]
    domains = {source.url.split("/", 3)[2].casefold() for source in qualified}
    required_domains = min(2, minimum_sources)
    return len(qualified) >= minimum_sources and len(domains) >= required_domains


def _topic_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\wÀ-ỹ]+", query.casefold())
        if token not in _TOPIC_STOP_WORDS and len(token) > 1
    }


def _topic_overlap(content: str, topic_terms: set[str]) -> float:
    folded_topic_terms = {_fold(term) for term in topic_terms}
    content_terms = set(re.findall(r"[\wÀ-ỹ]+", _fold(content)))
    return len(folded_topic_terms & content_terms) / len(folded_topic_terms)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
