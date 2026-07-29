from enum import StrEnum


class BudgetLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class TravelPace(StrEnum):
    relaxed = "relaxed"
    balanced = "balanced"
    packed = "packed"


class PlanKind(StrEnum):
    main = "main"
    backup = "backup"


class PlanStatus(StrEnum):
    draft = "draft"
    checking = "checking"
    locked = "locked"
    failed = "failed"
