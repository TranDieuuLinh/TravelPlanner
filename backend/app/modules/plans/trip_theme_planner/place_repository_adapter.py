"""
Adapter for the Knowledge Graph place projection used by research tools.

Adds methods required by research tools:
- list_for_overview
- list_within_radius  
- list_all_active
"""

from __future__ import annotations

import math
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.place_repository import (
    KnowledgeGraphPlaceRecord,
    KnowledgeGraphPlaceRepository,
)
from app.modules.plans.trip_theme_planner.research_tools_orchestrator import PlaceRepositoryForTools


EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in km."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


class PlaceRepositoryAdapter:
    """
    Adapter that projects KG entities into the research-tools protocol.
    
    This allows the existing repository to work with the new research tools
    without modifying the original class.
    """

    def __init__(self, session: Session) -> None:
        self._repository = KnowledgeGraphPlaceRepository(session)

    def list_for_overview(self, region_key: str) -> list[KnowledgeGraphPlaceRecord]:
        """
        List all places for a region (including sub-regions).
        
        Args:
            region_key: e.g., "vn,vung-tau"
            
        Returns:
            List of Place objects
        """
        return sorted(
            self._repository.list_for_place_selection(region_key, limit=100000),
            key=lambda place: (place.place_type, place.name),
        )

    def list_within_radius(
        self,
        center_lat: float,
        center_lng: float,
        radius_km: float,
    ) -> list[KnowledgeGraphPlaceRecord]:
        """
        List active places within a geographic radius.
        
        Uses bounding box pre-filter + haversine verification for accuracy.
        
        Args:
            center_lat: Center latitude
            center_lng: Center longitude  
            radius_km: Search radius in kilometers
            
        Returns:
            List of Place objects within radius
        """
        candidates = self._repository.list_active_for_planner_research(
            limit=100000
        )

        # Verify with haversine and filter
        results = []
        for place in candidates:
            if place.latitude is not None and place.longitude is not None:
                distance = _haversine_km(
                    center_lat,
                    center_lng,
                    float(place.latitude),
                    float(place.longitude),
                )
                if distance <= radius_km:
                    results.append(place)

        return results

    def list_all_active(self) -> list[KnowledgeGraphPlaceRecord]:
        """
        List all active places in the database.
        
        Returns:
            List of all active Place objects
        """
        return sorted(
            self._repository.list_active_for_planner_research(limit=100000),
            key=lambda place: (place.region_key, place.place_type),
        )


def create_tools_repository(session: Session) -> PlaceRepositoryAdapter:
    """Factory function to create a repository adapter for research tools."""
    return PlaceRepositoryAdapter(session)
