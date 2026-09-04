from app.shared.contracts.agent import AgentError


class ExplorerOperationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = max(0, retry_after_seconds)


class ExplorerPersistenceError(ExplorerOperationError):
    pass


def agent_error_from_exception(
    exc: Exception, fallback_code: str
) -> AgentError:
    if isinstance(exc, ExplorerOperationError):
        return AgentError(code=exc.code, message=str(exc), retryable=exc.retryable)
    return AgentError(
        code=fallback_code,
        message="Không thể tạo dữ liệu Explorer.",
    )
