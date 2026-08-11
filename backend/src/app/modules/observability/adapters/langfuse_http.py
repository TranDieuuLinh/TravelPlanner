from collections.abc import Mapping
from typing import Any

import httpx

from app.modules.observability.ports import LangfuseProviderError


class LangfuseHttpClient:
    def __init__(
        self,
        host: str,
        public_key: str | None,
        secret_key: str | None,
        timeout_seconds: float,
    ) -> None:
        self.host = host.rstrip("/")
        self.public_key = public_key.strip() if public_key else None
        self.secret_key = secret_key.strip() if secret_key else None
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.public_key and self.secret_key)

    async def get(
        self, resource: str, params: Mapping[str, str | int | None]
    ) -> dict[str, Any]:
        if not self.configured:
            raise LangfuseProviderError(
                "LANGFUSE_NOT_CONFIGURED",
                "Langfuse chưa được cấu hình API key.",
                status_code=503,
            )
        query = {key: value for key, value in params.items() if value is not None}
        try:
            async with httpx.AsyncClient(
                base_url=self.host,
                auth=(self.public_key or "", self.secret_key or ""),
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.get(f"/api/public/{resource}", params=query)
        except httpx.TimeoutException as exc:
            raise LangfuseProviderError(
                "LANGFUSE_TIMEOUT", "Langfuse không phản hồi kịp thời."
            ) from exc
        except httpx.HTTPError as exc:
            raise LangfuseProviderError(
                "LANGFUSE_UNAVAILABLE", "Không kết nối được Langfuse."
            ) from exc

        if response.status_code == 401:
            raise LangfuseProviderError(
                "LANGFUSE_UNAUTHORIZED", "Langfuse API key không hợp lệ.", 502
            )
        if response.status_code >= 400:
            raise LangfuseProviderError(
                "LANGFUSE_REQUEST_FAILED",
                f"Langfuse trả về HTTP {response.status_code}.",
                502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise LangfuseProviderError(
                "LANGFUSE_INVALID_RESPONSE", "Langfuse trả về dữ liệu không hợp lệ."
            ) from exc
        if not isinstance(payload, dict):
            raise LangfuseProviderError(
                "LANGFUSE_INVALID_RESPONSE", "Langfuse trả về dữ liệu không hợp lệ."
            )
        return payload

    async def ingest(self, payload: dict[str, Any]) -> None:
        if not self.configured:
            raise LangfuseProviderError(
                "LANGFUSE_NOT_CONFIGURED",
                "Langfuse chưa được cấu hình API key.",
                status_code=503,
            )
        try:
            async with httpx.AsyncClient(
                base_url=self.host,
                auth=(self.public_key or "", self.secret_key or ""),
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.post("/api/public/ingestion", json=payload)
        except httpx.TimeoutException as exc:
            raise LangfuseProviderError(
                "LANGFUSE_TIMEOUT", "Langfuse không phản hồi kịp thời."
            ) from exc
        except httpx.HTTPError as exc:
            raise LangfuseProviderError(
                "LANGFUSE_UNAVAILABLE", "Không kết nối được Langfuse."
            ) from exc
        if response.status_code == 401:
            raise LangfuseProviderError(
                "LANGFUSE_UNAUTHORIZED", "Langfuse API key không hợp lệ.", 502
            )
        if response.status_code >= 400:
            raise LangfuseProviderError(
                "LANGFUSE_REQUEST_FAILED",
                f"Langfuse trả về HTTP {response.status_code}.",
                502,
            )
