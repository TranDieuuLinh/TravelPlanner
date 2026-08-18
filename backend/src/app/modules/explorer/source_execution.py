import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import SourceExtractionResult
from app.modules.explorer.retry import run_with_one_retry
from app.shared.contracts.agent import AgentError


async def safe_source(
    *,
    kind: str,
    index: int,
    reference: str,
    operation: Callable[[], Awaitable[Any]],
    timeout_seconds: float,
) -> SourceExtractionResult:
    try:
        return await asyncio.wait_for(
            run_with_one_retry(operation), timeout=timeout_seconds
        )
    except TimeoutError:
        return SourceExtractionResult(
            sourceIndex=index,
            sourceKind=kind,
            sourceRef=reference,
            status="failed_retryable",
            error=AgentError(
                code="SOURCE_EXTRACTION_TIMEOUT",
                message=(
                    "Nguồn vượt quá ngân sách thời gian trích xuất; "
                    "các nguồn còn lại vẫn được xử lý."
                ),
                retryable=True,
            ),
        )
    except ExplorerOperationError as exc:
        return SourceExtractionResult(
            sourceIndex=index,
            sourceKind=kind,
            sourceRef=reference,
            status="failed_retryable" if exc.retryable else "failed_permanent",
            error=AgentError(code=exc.code, message=str(exc), retryable=exc.retryable),
        )
    except Exception:
        return SourceExtractionResult(
            sourceIndex=index,
            sourceKind=kind,
            sourceRef=reference,
            status="failed_permanent",
            error=AgentError(
                code="SOURCE_EXTRACTION_FAILED",
                message="Không thể trích xuất nguồn đầu vào.",
            ),
        )


def mark_synthesis_timeout(results: list[SourceExtractionResult]) -> None:
    for result in results:
        result.status = "partial"
        result.source_chunk_count = max(1, result.source_chunk_count)
        result.processed_source_chunk_count = 0
        result.synthesis_coverage_ratio = 0.0
