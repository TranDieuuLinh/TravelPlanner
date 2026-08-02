from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.llm.factory import get_llm_client
from app.integrations.media import LocalPostMediaStorage, PostMediaStorage
from app.core.config import settings
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schema import (
    ExplorePostRead,
    ProfileShowcaseRead,
    UserPostCreate,
    UserPostRead,
    VisitedPlaceCreate,
    VisitedPlaceRead,
)
from app.modules.profiles.service import ProfileService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate, UserRead

router = APIRouter(prefix="/me", tags=["profile"])
public_router = APIRouter(prefix="/posts", tags=["posts"])


def get_post_media_storage() -> LocalPostMediaStorage:
    return LocalPostMediaStorage(
        settings.user_post_media_dir,
        image_max_bytes=settings.user_post_image_max_bytes,
        video_max_bytes=settings.user_post_video_max_bytes,
    )

@router.post("/planner-preview")
async def planner_preview(destination: str, days: int = 3, budget: str = "medium") -> dict[str, str]:
    client = get_llm_client()
    prompt = f"Destination: {destination}. Days: {days}. Budget: {budget}."
    draft = await client.generate_profile_plan(prompt)
    return {"draft": draft}

def get_profile_service(db: Annotated[Session, Depends(get_db)]) -> ProfileService:
    return ProfileService(UserRepository(db), ProfileRepository(db))


@router.get("", response_model=UserRead)
def get_me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.get("/showcase", response_model=ProfileShowcaseRead)
def get_profile_showcase(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileShowcaseRead:
    return service.get_showcase(user)


@router.post(
    "/visited-places",
    response_model=VisitedPlaceRead,
    status_code=status.HTTP_201_CREATED,
)
def mark_place_visited(
    payload: VisitedPlaceCreate,
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> VisitedPlaceRead:
    return service.mark_place_visited(user, payload)


@router.post("/posts", response_model=UserPostRead, status_code=status.HTTP_201_CREATED)
async def create_profile_post(
    request: Request,
    content_type: Annotated[Literal["post", "reel"], Form(alias="contentType")],
    caption: Annotated[str, Form(min_length=1, max_length=2200)],
    location_name: Annotated[str, Form(alias="locationName", min_length=1, max_length=255)],
    media: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_csrf)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    storage: Annotated[PostMediaStorage, Depends(get_post_media_storage)],
) -> UserPostRead:
    caption, location_name = service.normalize_post_text(caption, location_name)
    stored = await storage.save(media, content_type=content_type)
    media_url = str(request.url_for("user_post_media", path=stored.filename))
    payload = UserPostCreate(
        contentType=content_type,
        caption=caption,
        mediaUrl=media_url,
        locationName=location_name,
    )
    try:
        return service.create_post(user, payload)
    except Exception:
        storage.delete(stored.filename)
        raise


@public_router.get("", response_model=list[ExplorePostRead])
def list_explore_posts(
    service: Annotated[ProfileService, Depends(get_profile_service)],
    limit: Annotated[int, Query(ge=1, le=60)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ExplorePostRead]:
    return service.list_public_posts(limit=limit, offset=offset)


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
