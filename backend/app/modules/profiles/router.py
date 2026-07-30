from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.llm.factory import get_llm_client
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schema import ProfileShowcaseRead, VisitedPlaceCreate, VisitedPlaceRead
from app.modules.profiles.service import ProfileService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import CreatorApplicationCreate, ProfileUpdate, UserRead

router = APIRouter(prefix="/me", tags=["profile"])

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
