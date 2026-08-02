"""
Research Tools Orchestrator - Manages all Planner research tools.

Provides a unified interface for:
1. region_overview - Overview statistics for a known region
2. constraint_research - Spatial + category stats with constraints
3. festival_discovery - Festival/holiday discovery

Usage:
    from app.modules.plans.planner.research_tools_orchestrator import ResearchToolsOrchestrator

    orchestrator = ResearchToolsOrchestrator(place_repository)
    
    # Tool 1: Region Overview
    result = orchestrator.region_overview(
        RegionOverviewInput(region_key="vn,vung-tau")
    )
    
    # Tool 2: Constraint Research
    result = orchestrator.constraint_research(
        ConstraintResearchInput(
            mode="coordinates",
            center_lat=10.8231,
            center_lng=106.6297,
            radius_km=50,
            budget=10000000,
            duration=3,
            interests=["beach", "food"],
        )
    )
    
    # Tool 3: Festival Discovery
    result = orchestrator.festival_discovery(
        FestivalDiscoveryInput(month="tháng 4")
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.modules.plans.planner.constraint_tool import ConstraintResearchTool
from app.modules.plans.planner.festival_tool import FestivalDiscoveryTool
from app.modules.plans.planner.region_overview_tool import RegionOverviewTool
from app.modules.plans.planner.research_tools_schema import (
    ConstraintResearchInput,
    ConstraintResearchOutput,
    FestivalDiscoveryInput,
    FestivalDiscoveryOutput,
    RegionOverviewInput,
    RegionOverviewOutput,
)

if TYPE_CHECKING:
    from app.modules.places.model import Place


class PlaceRepositoryForTools(Protocol):
    """Protocol for place repository compatible with all research tools."""

    def list_for_overview(self, region_key: str) -> list[Place]:
        """List places for region overview."""
        ...

    def list_within_radius(
        self,
        center_lat: float,
        center_lng: float,
        radius_km: float,
    ) -> list[Place]:
        """List places within a geographic radius."""
        ...

    def list_all_active(self) -> list[Place]:
        """List all active places."""
        ...

    def list_active_for_region(self, region_key: str) -> list[Place]:
        """List active places inside a resolved region and its descendants."""
        ...


class ResearchToolsOrchestrator:
    """
    Unified orchestrator for all Planner research tools.

    Combines region_overview, constraint_research, and festival_discovery
    into a single interface with dependency injection for the place repository.
    """

    def __init__(self, place_repository: PlaceRepositoryForTools) -> None:
        self._place_repository = place_repository

        # Initialize individual tools
        self._region_overview = RegionOverviewTool(place_repository)
        self._constraint_research = ConstraintResearchTool(place_repository)
        self._festival_discovery = FestivalDiscoveryTool()

    def region_overview(
        self,
        input_data: RegionOverviewInput,
    ) -> RegionOverviewOutput:
        """
        Tool 1: Get overview statistics for a known region.

        Args:
            input_data: Region key to analyze

        Returns:
            Category stats, price distribution, and ratings for the region
        """
        return self._region_overview.execute(input_data)

    def constraint_research(
        self,
        input_data: ConstraintResearchInput,
    ) -> ConstraintResearchOutput:
        """
        Tool 2: Research places with constraints (coordinates, budget, interests).

        Args:
            input_data: Coordinates/budget/interests filter

        Returns:
            Spatial stats (zones), category stats, and budget compatibility
        """
        return self._constraint_research.execute(input_data)

    def festival_discovery(
        self,
        input_data: FestivalDiscoveryInput,
    ) -> FestivalDiscoveryOutput:
        """
        Tool 3: Discover festivals and holidays.

        Args:
            input_data: Optional month filter

        Returns:
            List of festivals and by-month index
        """
        return self._festival_discovery.execute(input_data)


# Convenience function to create orchestrator with a repository
def create_research_tools(repository: PlaceRepositoryForTools) -> ResearchToolsOrchestrator:
    """Factory function to create ResearchToolsOrchestrator."""
    return ResearchToolsOrchestrator(repository)
