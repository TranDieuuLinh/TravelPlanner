from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.auth.public import AuthUser, require_current_user
from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceSearchRequest,
    SearchPlacesTool,
)


router = APIRouter(prefix="/v1/plans", tags=["place-search"])


def _search_dependencies(request: Request) -> tuple[SearchPlacesTool, PostgresPlaceCatalog]:
    tool = getattr(request.app.state, "manual_place_search_tool", None)
    catalog = getattr(request.app.state, "manual_place_search_catalog", None)
    if tool is None or catalog is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PLACE_SEARCH_UNAVAILABLE",
                "message": "Tìm kiếm địa điểm chưa được cấu hình.",
            },
        )
    return tool, catalog


@router.get("/places/search")
async def search_places_for_manual_plan(
    query: str = Query(..., min_length=2, max_length=200),
    destination: str | None = Query(default=None, max_length=160),
    top_k: int = Query(default=5, ge=1, le=20, alias="topK"),
    _: AuthUser = Depends(require_current_user),
    dependencies: tuple[SearchPlacesTool, PostgresPlaceCatalog] = Depends(_search_dependencies),
) -> list[dict[str, object | None]]:
    tool, catalog = dependencies
    destination_name = (destination or "Việt Nam").strip()
    adm = await catalog.resolve(destination_name)
    input_adm = AdministrativeArea(
        adm_id=adm.adm_id or "VN",
        name=adm.canonical_name or destination_name,
        level="ADM1" if adm.adm_id else "ADM0",
        country_code=adm.country_code or "VN",
    )
    result = await tool.search(
        PlaceSearchRequest(
            query=query,
            input_adm=input_adm,
            top_k=top_k,
            allow_external_fallback=True,
        )
    )
    metadata_by_id = await catalog.get_many(
        list(
            dict.fromkeys(
                match.place_id for match in result.top_matches if match.place_id
            )
        )
    )
    suggestions: list[dict[str, object | None]] = []
    for match in result.top_matches:
        coordinates = match.coordinates
        metadata = metadata_by_id.get(match.place_id or "")
        suggestions.append(
            {
                "name": match.name,
                "address": match.address,
                "latitude": coordinates.latitude if coordinates else None,
                "longitude": coordinates.longitude if coordinates else None,
                "placeId": match.place_id or match.provider_id,
                "imageUrl": None,
                "rating": match.rating,
                "reviewCount": match.review_count,
                "placeType": match.canonical_type,
                "durationMinutes": (
                    metadata.typical_duration_minutes if metadata else None
                ),
                "openingHours": metadata.opening_hours if metadata else None,
                "costPerPerson": (
                    ceil(metadata.typical_cost)
                    if metadata and metadata.typical_cost is not None
                    else None
                ),
                "isVerified": match.verification_status == "verified",
                "source": match.provider,
            }
        )
    return suggestions
