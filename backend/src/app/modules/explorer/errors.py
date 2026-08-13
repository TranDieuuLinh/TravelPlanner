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
