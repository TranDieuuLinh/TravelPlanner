class ApplicationError(RuntimeError):
    """Base error safe for translation at the API boundary."""


class ModuleContractError(ApplicationError):
    """Raised when a module receives an invalid public contract."""

