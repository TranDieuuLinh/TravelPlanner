class AnswerProviderError(RuntimeError):
    code = "answer_provider_error"


class AnswerProviderTimeout(AnswerProviderError):
    code = "answer_provider_timeout"


class AnswerProviderUnauthorized(AnswerProviderError):
    code = "answer_provider_unauthorized"


class AnswerProviderQuotaExceeded(AnswerProviderError):
    code = "answer_provider_quota_exceeded"


class AnswerProviderInvalidOutput(AnswerProviderError):
    code = "answer_provider_invalid_output"


class AnswerProviderRefusal(AnswerProviderError):
    code = "answer_provider_refusal"


class EmbeddingProviderError(RuntimeError):
    code = "embedding_provider_error"


class EmbeddingProviderTimeout(EmbeddingProviderError):
    code = "embedding_provider_timeout"


class EmbeddingProviderUnauthorized(EmbeddingProviderError):
    code = "embedding_provider_unauthorized"


class EmbeddingProviderQuotaExceeded(EmbeddingProviderError):
    code = "embedding_provider_quota_exceeded"


class EmbeddingProviderInvalidOutput(EmbeddingProviderError):
    code = "embedding_provider_invalid_output"


class SourceChunkingError(RuntimeError):
    code = "source_chunking_error"
