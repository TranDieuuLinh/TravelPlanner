from app.shared.tools.search_places.ports import PlaceSearchProviderError


class PlaceCatalogUnavailableError(PlaceSearchProviderError):
    """Raised when an identity or metadata catalog cannot serve a request."""


class CandidateSourceError(RuntimeError):
    code = "candidate_source_error"


class CandidateSourceTimeout(CandidateSourceError):
    code = "candidate_source_timeout"
