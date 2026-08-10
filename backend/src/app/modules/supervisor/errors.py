class SupervisorError(RuntimeError):
    """Base error for supervisor classification."""


class SupervisorClassificationError(SupervisorError):
    """Raised when LLM classification fails and fallback is disabled."""
