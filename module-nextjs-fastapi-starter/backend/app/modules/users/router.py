from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.users.dependencies import get_user_service
from app.modules.users.schema import UserCreate, UserRead
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(service: Annotated[UserService, Depends(get_user_service)]) -> list[UserRead]:
    return service.list_users()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, service: Annotated[UserService, Depends(get_user_service)]) -> UserRead:
    return service.create_user(payload)
