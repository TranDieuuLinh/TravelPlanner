import asyncio
from functools import cached_property

from app.modules.information_finder.contract import EmbeddingIdentity


class MultilingualE5EmbeddingProvider:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        model_revision: str | None = None,
        dimensions: int = 384,
    ) -> None:
        self._identity = EmbeddingIdentity(
            model_name=model_name,
            model_revision=model_revision,
            dimensions=dimensions,
        )
        self._load_lock = asyncio.Lock()

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    @cached_property
    def _model(self):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Install the 'embeddings' extra to use multilingual-e5."
            ) from exc
        return SentenceTransformer(
            self.identity.model_name,
            revision=self.identity.model_revision,
        )

    async def _encode(self, texts: list[str]) -> list[list[float]]:
        async with self._load_lock:
            vectors = await asyncio.to_thread(
                self._model.encode,
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        output = [vector.tolist() for vector in vectors]
        if any(len(vector) != self.identity.dimensions for vector in output):
            raise RuntimeError("Embedding model returned unexpected dimensions")
        return output

    async def embed_query(self, text: str) -> list[float]:
        return (await self._encode([f"query: {text}"]))[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._encode([f"passage: {text}" for text in texts])
