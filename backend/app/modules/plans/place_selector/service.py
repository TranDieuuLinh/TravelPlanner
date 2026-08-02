from __future__ import annotations

from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import EmptyFinderPlaceTool
from app.modules.plans.place_selector.meal_selector import MealStopSelector


class PlaceSelectorService(FinderService):
    """Select feasible Places before route-first itinerary optimization.

    ``FinderService`` remains the compatibility implementation and rollback
    boundary. New runtime wiring uses this product-facing name so the
    deterministic selector is not presented as a separate AI agent.
    """

    def __init__(self, place_tool=None, **kwargs) -> None:
        resolved_place_tool = place_tool or EmptyFinderPlaceTool()
        kwargs.setdefault("meal_selector", MealStopSelector(resolved_place_tool))
        super().__init__(resolved_place_tool, **kwargs)
