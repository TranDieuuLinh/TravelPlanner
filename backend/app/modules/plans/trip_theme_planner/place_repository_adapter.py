"""
Adapter for SqlAlchemyPlaceRepository to implement PlaceRepositoryForTools protocol.

Adds methods required by research tools:
- list_for_overview
- list_within_radius  
- list_all_active
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from app.modules.places.model import Place
from app.modules.plans.trip_theme_planner.research_tools_orchestrator import PlaceRepositoryForTools

if TYPE_CHECKING:
    pass


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
    Adapter that wraps SqlAlchemyPlaceRepository to implement PlaceRepositoryForTools.
    
    This allows the existing repository to work with the new research tools
    without modifying the original class.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_overview(self, region_key: str) -> list[Place]:
        """
        List all places for a region (including sub-regions).
        
        Args:
            region_key: e.g., "vn,vung-tau"
            
        Returns:
            List of Place objects
        """
        query = (
            select(Place)
            .where(
                Place.deleted_at.is_(None),
                or_(
                    Place.region_key == region_key,
                    Place.region_key.like(f"{region_key},%"),
                ),
            )
            .order_by(Place.place_type, Place.name)
        )
        return list(self._session.scalars(query))

    def list_within_radius(
        self,
        center_lat: float,
        center_lng: float,
        radius_km: float,
    ) -> list[Place]:
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
        # Calculate bounding box for pre-filtering
        lat_delta = radius_km / 111.0  # ~111km per degree latitude
        lng_delta = radius_km / (111.0 * math.cos(math.radians(center_lat)))

        min_lat = center_lat - lat_delta
        max_lat = center_lat + lat_delta
        min_lng = center_lng - lng_delta
        max_lng = center_lng + lng_delta

        # Pre-filter with bounding box
        query = (
            select(Place)
            .where(
                Place.deleted_at.is_(None),
                Place.status == "active",
                Place.latitude.isnot(None),
                Place.longitude.isnot(None),
                Place.latitude >= min_lat,
                Place.latitude <= max_lat,
                Place.longitude >= min_lng,
                Place.longitude <= max_lng,
            )
            .order_by(Place.region_key, Place.place_type)
        )

        candidates = list(self._session.scalars(query))

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

    def list_all_active(self) -> list[Place]:
        """
        List all active places in the database.
        
        Returns:
            List of all active Place objects
        """
        query = (
            select(Place)
            .where(
                Place.deleted_at.is_(None),
                Place.status == "active",
            )
            .order_by(Place.region_key, Place.place_type)
        )
        return list(self._session.scalars(query))


def create_tools_repository(session: Session) -> PlaceRepositoryAdapter:
    """Factory function to create a repository adapter for research tools."""
    return PlaceRepositoryAdapter(session)
