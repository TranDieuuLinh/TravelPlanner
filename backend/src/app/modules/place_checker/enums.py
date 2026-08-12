from enum import StrEnum


class PlaceLifecycleState(StrEnum):
    received = "received"
    normalized = "normalized"
    resolving = "resolving"
    unresolved = "unresolved"
    needs_review = "needs_review"
    resolved = "resolved"
    enriched = "enriched"
    provisional = "provisional"
    verified_kg = "verified_kg"
    verified_external = "verified_external"
    evaluated = "evaluated"
    planner_ready = "planner_ready"
    conditional = "conditional"
    blocked = "blocked"
    rejected = "rejected"


class VerificationStatus(StrEnum):
    unresolved = "unresolved"
    needs_review = "needs_review"
    provisional = "provisional"
    verified_kg = "verified_kg"
    verified_external = "verified_external"


class SourceTier(StrEnum):
    direct_user = "direct_user"
    url = "url"
    item_resolved = "item_resolved"
    system_suggested = "system_suggested"


class IssueSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PlaceCheckerStatus(StrEnum):
    completed = "completed"
    conditional = "conditional"
    partial = "partial"
    blocked = "blocked"


class EvidenceOrigin(StrEnum):
    input = "input"
    url = "url"
    system = "system"


class AdmResolutionStatus(StrEnum):
    resolved = "resolved"
    ambiguous = "ambiguous"
    unresolved = "unresolved"


class BudgetMode(StrEnum):
    target_amount = "target_amount"
    relative_level = "relative_level"


class TravelPace(StrEnum):
    slow = "slow"
    balanced = "balanced"
    fast = "fast"


class IdentityResolutionStatus(StrEnum):
    resolved = "resolved"
    needs_review = "needs_review"
    unresolved = "unresolved"


class SimilarityMethod(StrEnum):
    exact = "exact"
    alias = "alias"
    lexical = "lexical"
    semantic = "semantic"
    lexical_only = "lexical_only"


class OperationalStatus(StrEnum):
    active = "active"
    temporarily_closed = "temporarily_closed"
    permanently_closed = "permanently_closed"
    unknown = "unknown"


class CostTier(StrEnum):
    free = "free"
    low = "low"
    medium = "medium"
    high = "high"
    premium = "premium"
    unknown = "unknown"


class ItemResolutionStatus(StrEnum):
    resolved = "resolved"
    partially_resolved = "partially_resolved"
    unresolved = "unresolved"


class EvaluationDimension(StrEnum):
    identity = "identity"
    destination = "destination"
    operational = "operational"
    duration = "duration"
    cost = "cost"
    preference = "preference"
    avoid = "avoid"
    people = "people"
    accessibility = "accessibility"
    data_quality = "data_quality"


class BudgetAssessmentStatus(StrEnum):
    within = "within"
    at_risk = "at_risk"
    over = "over"
    unknown = "unknown"


class CapacityLoadStatus(StrEnum):
    underloaded = "underloaded"
    balanced = "balanced"
    at_risk = "at_risk"
    overloaded = "overloaded"
    unknown = "unknown"


class CoverageLevel(StrEnum):
    sufficient = "sufficient"
    partial = "partial"
    insufficient = "insufficient"


class GeographicSpread(StrEnum):
    unknown = "unknown"
    compact = "compact"
    moderate = "moderate"
    dispersed = "dispersed"


class GapType(StrEnum):
    mandatory_identity_metadata = "mandatory_identity_metadata"
    trip_capacity = "trip_capacity"
    experience_coverage = "experience_coverage"
    food_coverage = "food_coverage"
    time_of_day = "time_of_day"
    budget = "budget"
    diversity = "diversity"
    geographic_balance = "geographic_balance"
    people_accessibility = "people_accessibility"
    data_quality = "data_quality"
    destination_compatibility = "destination_compatibility"


class GapStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    deferred = "deferred"


class RetrievalSourceKind(StrEnum):
    knowledge_graph = "knowledge_graph"
    internal = "internal"
    external = "external"


class PromotionEventStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    promoted = "promoted"
    failed = "failed"


class UnresolvedEntityType(StrEnum):
    place = "place"
    item = "item"
    adm = "adm"
    validation = "validation"
