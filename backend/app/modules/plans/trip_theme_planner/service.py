from __future__ import annotations

from app.modules.plans.planner.planner_service import PlannerService


class TripThemePlannerService(PlannerService):
    """Define must-cover trip themes without assigning them to calendar days.

    ``PlannerService`` remains the compatibility/rollback implementation while
    runtime wiring uses this product-facing name for the route-first pipeline.
    """
