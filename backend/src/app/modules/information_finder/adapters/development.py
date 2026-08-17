import hashlib
import math
from uuid import uuid4

from app.modules.information_finder.contract import (
    AnswerClaim,
    EmbeddingIdentity,
    FactItem,
    FactListBlock,
    GeneratedAnswer,
    ParagraphBlock,
    PreparedSource,
    RetrievedSource,
)
from app.modules.information_finder.freshness import FreshnessPolicy
from app.modules.information_finder.normalization import select_relevant_excerpt
from app.modules.information_finder.structured_content import clean_source_sentences


class HashingEmbeddingProvider:
    """Deterministic no-download fallback; not a production semantic model."""

    def __init__(self, dimensions: int = 384) -> None:
        self._identity = EmbeddingIdentity(
            model_name="development-hashing-embedding",
            model_revision="1",
            dimensions=dimensions,
        )

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def _embed(self, prefixed_text: str) -> list[float]:
        vector = [0.0] * self.identity.dimensions
        for token in prefixed_text.casefold().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % len(vector)
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(f"query: {text}")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(f"passage: {text}") for text in texts]


class InMemorySourceRepository:
    """Process-local development/test cache with production-equivalent semantics."""

    def __init__(self) -> None:
        self.sources: dict[str, RetrievedSource] = {}
        self.embeddings: dict[str, tuple[EmbeddingIdentity, list[float]]] = {}
        self.content_hashes: dict[str, str] = {}
        self.snapshot_counts: dict[str, int] = {}
        self.failed_searches: list[str] = []

    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        identity: EmbeddingIdentity,
        limit: int,
    ) -> list[RetrievedSource]:
        query_terms = set(query.casefold().split())
        found: list[RetrievedSource] = []
        for url, source in self.sources.items():
            stored_identity, embedding = self.embeddings[url]
            if stored_identity != identity:
                continue
            semantic = sum(a * b for a, b in zip(query_embedding, embedding))
            terms = set(source.content.casefold().split())
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            found.append(
                source.model_copy(
                    update={
                        "semantic_score": max(0.0, semantic),
                        "lexical_score": lexical,
                        "freshness_score": FreshnessPolicy.score(source.expires_at),
                    }
                )
            )
        return sorted(found, key=lambda item: item.semantic_score, reverse=True)[:limit]

    async def save_search(
        self,
        *,
        original_query: str,
        normalized_query: str,
        sources: list[PreparedSource],
        identity: EmbeddingIdentity,
        provider_request_id: str | None,
        search_parameters: dict,
    ) -> list[RetrievedSource]:
        saved: list[RetrievedSource] = []
        for prepared in sources:
            existing = self.sources.get(prepared.canonical_url)
            unchanged = (
                existing is not None
                and self.content_hashes.get(prepared.canonical_url)
                == prepared.content_hash
            )
            snapshot_id = (
                existing.snapshot_id
                if unchanged and existing is not None
                else str(uuid4())
            )
            if not unchanged:
                self.snapshot_counts[prepared.canonical_url] = (
                    self.snapshot_counts.get(prepared.canonical_url, 0) + 1
                )
            source = RetrievedSource(
                source_id=existing.source_id if existing else str(uuid4()),
                snapshot_id=snapshot_id,
                title=prepared.result.title,
                url=prepared.canonical_url,
                content=prepared.result.content,
                provider_score=prepared.result.provider_score,
                published_at=prepared.result.published_at,
                source_updated_at=prepared.result.source_updated_at,
                last_fetched_at=prepared.result.fetched_at,
                expires_at=prepared.expires_at,
            )
            self.sources[prepared.canonical_url] = source
            self.content_hashes[prepared.canonical_url] = prepared.content_hash
            if prepared.chunks:
                self.embeddings[prepared.canonical_url] = (
                    identity,
                    prepared.chunks[0].embedding,
                )
            saved.append(source)
        return saved

    async def record_failed_search(self, **kwargs) -> None:
        self.failed_searches.append(kwargs["error_code"])


class ExtractiveAnswerGenerator:
    """Truthful development fallback that only quotes supplied source snippets."""

    max_claims = 3
    max_chars_per_claim = 280
    max_words_per_fact = 25

    async def generate(
        self, query: str, sources: list[RetrievedSource]
    ) -> GeneratedAnswer:
        claims = []
        fact_items = []
        for source in sources:
            sentences = clean_source_sentences(source.content, query, source.title)
            snippet = sentences[0] if sentences else select_relevant_excerpt(
                source.content,
                query,
                title=source.title,
                max_chars=self.max_chars_per_claim,
            )
            snippet = _limit_words(snippet, self.max_words_per_fact)
            if not snippet:
                continue
            prefix = "## Thông tin nổi bật\n\n" if not claims else ""
            claims.append(
                AnswerClaim(
                    text=f"{prefix}- {snippet}",
                    source_ids=[source.source_id],
                )
            )
            fact_items.append(
                FactItem(
                    label="Thông tin",
                    text=snippet,
                    source_ids=[source.source_id],
                )
            )
            if len(claims) >= self.max_claims:
                break
        if not claims and sources:
            fallback_text = "Thông tin hiện có chưa đủ rõ để trả lời câu hỏi này."
            claims.append(
                AnswerClaim(
                    text=fallback_text,
                    source_ids=[sources[0].source_id],
                )
            )
            return GeneratedAnswer(
                claims=claims,
                blocks=[
                    ParagraphBlock(
                        text=fallback_text,
                        source_ids=[sources[0].source_id],
                    )
                ],
            )
        return GeneratedAnswer(
            claims=claims,
            blocks=[FactListBlock(title="Thông tin nổi bật", items=fact_items)],
        )


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(" ,;:")
