from enum import Enum


class ListingStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


class VersionModerationStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ListingCategory(str, Enum):
    BUDGET = "budget"
    BALANCED = "balanced"
    COMFORTABLE = "comfortable"
    FOOD = "food"
    NATURE = "nature"
    FAMILY = "family"
    CREATOR_PICKS = "creator-picks"


class ListingSortOption(str, Enum):
    NEWEST = "newest"
    PRICE_ASC = "priceAsc"
    PRICE_DESC = "priceDesc"
    RATING = "rating"
