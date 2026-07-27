from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.profiles.service import ProfileService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate, UserRead

router = APIRouter(prefix="/me", tags=["profile"])


def get_profile_service(db: Annotated[Session, Depends(get_db)]) -> ProfileService:
    return ProfileService(UserRepository(db))


@router.get("", response_model=UserRead)
def get_me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.patch("/profile", response_model=UserRead)
def update_profile(
    payload: ProfileUpdate,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> User:
    return service.update_profile(user, payload)


@router.post("/creator-application", response_model=UserRead)
def submit_creator_application(
    payload: CreatorApplicationCreate,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> User:
    return service.submit_creator_application(user, payload)
