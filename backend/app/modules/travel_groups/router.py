from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import get_optional_active_user, require_csrf
from app.modules.travel_groups.dependencies import get_travel_group_service
from app.modules.travel_groups.schema import (
    TravelGroupDetailResponse,
    TravelGroupListResponse,
    TravelGroupMembershipResponse,
    TravelGroupPostCreate,
    TravelGroupPostResponse,
)
from app.modules.travel_groups.service import TravelGroupService
from app.modules.users.model import User

router = APIRouter(prefix="/travel-groups", tags=["travel-groups"])


@router.get("", response_model=TravelGroupListResponse)
def search_travel_groups(
    query: str | None = Query(default=None, max_length=160),
    user: Annotated[User | None, Depends(get_optional_active_user)] = None,
    service: Annotated[TravelGroupService, Depends(get_travel_group_service)] = None,  # type: ignore[assignment]
) -> TravelGroupListResponse:
    return service.search(query=query, user=user)


@router.get("/{group_id}", response_model=TravelGroupDetailResponse)
def get_travel_group(
    group_id: int,
    user: Annotated[User | None, Depends(get_optional_active_user)] = None,
    service: Annotated[TravelGroupService, Depends(get_travel_group_service)] = None,  # type: ignore[assignment]
) -> TravelGroupDetailResponse:
    return service.detail(group_id=group_id, user=user)


@router.post(
    "/{group_id}/posts",
    response_model=TravelGroupPostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_travel_group_post(
    group_id: int,
    payload: TravelGroupPostCreate,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[TravelGroupService, Depends(get_travel_group_service)],
) -> TravelGroupPostResponse:
    return service.create_post(group_id=group_id, user=user, payload=payload)


@router.put("/{group_id}/membership", response_model=TravelGroupMembershipResponse)
def join_travel_group(
    group_id: int,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[TravelGroupService, Depends(get_travel_group_service)],
) -> TravelGroupMembershipResponse:
    return service.join(group_id=group_id, user=user)
