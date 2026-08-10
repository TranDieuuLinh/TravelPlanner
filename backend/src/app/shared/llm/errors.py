class LlmError(RuntimeError):
    """Base error for shared LLM calls."""

    code = "llm_error"


class LlmConfigurationError(LlmError):
    code = "llm_configuration_error"


class LlmProviderError(LlmError):
    code = "llm_provider_error"


class LlmUnauthorizedError(LlmProviderError):
    code = "llm_unauthorized"


class LlmQuotaError(LlmProviderError):
    code = "llm_quota_exceeded"


class LlmServerError(LlmProviderError):
    code = "llm_server_error"


class LlmResponseError(LlmProviderError):
    code = "llm_invalid_response"


class LlmRefusalError(LlmResponseError):
    code = "llm_refusal"


class LlmTransportError(LlmError):
    code = "llm_transport_error"


class LlmTimeoutError(LlmTransportError):
    code = "llm_timeout"


class LlmAllKeysUnavailable(LlmError):
    code = "llm_all_keys_unavailable"

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            "All configured LLM API keys are temporarily unavailable. "
            f"Retry after {retry_after_seconds:.1f} seconds."
        )
