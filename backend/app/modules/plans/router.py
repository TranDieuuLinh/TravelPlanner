import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.modules.auth.dependencies import get_optional_current_user
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    ExploreTripSpecInput,
    FullExploreRequest,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.schema import (
    BackupPlanCreate,
    FeatureMapItem,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanBundleRead,
    PlanRead,
    PlanningContextCreate,
)
from app.modules.plans.service import PlanService
from app.modules.users.model import User

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/feature-map", response_model=list[FeatureMapItem])
def feature_map(service: Annotated[PlanService, Depends(get_plan_service)]) -> list[FeatureMapItem]:
    return service.feature_map()




@router.post("/explore/full", response_model=ExploreIntakeResponse)
async def explore_full(
    payload: FullExploreRequest,
    service: Annotated[PlanService, Depends(get_plan_service)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> ExploreIntakeResponse:
    try:
        return await service.explore_full(
            _attach_authenticated_preference(payload, current_user)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/explore/full/intake", response_model=ExploreIntakeResponse)
async def explore_full_intake(
    service: Annotated[PlanService, Depends(get_plan_service)],
    current_user: Annotated[
        User | None,
        Depends(get_optional_current_user),
    ],
    raw_request: Annotated[str, Form(alias="rawRequest")] = "",
    destination: Annotated[str | None, Form()] = None,
    urls: Annotated[list[str] | None, Form()] = None,
    trip_spec_json: Annotated[str | None, Form(alias="tripSpec")] = None,
    user_state_json: Annotated[str | None, Form(alias="userState")] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> ExploreIntakeResponse:
    try:
        effective_request, normalized_urls = _prepare_intake(
            raw_request,
            explicit_urls=urls or [],
            has_images=bool(images),
        )
        normalized_destination = (
            destination or _infer_destination(_remove_urls(effective_request))
        ).strip()
        trip_spec = _parse_trip_spec(trip_spec_json) or _default_trip_spec(
            effective_request
        )
        user_state = _authenticated_user_state(
            _parse_user_state(user_state_json),
            current_user,
        )
        uploaded_images = await _read_and_close_images(images or [])
        return await service.explore_from_intake(
            raw_request=effective_request,
            destination=normalized_destination or "unspecified",
            urls=normalized_urls,
            images=uploaded_images,
            trip_spec=trip_spec,
            user_state=user_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/main", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def create_main_plan(
    payload: MainPlanCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return await service.create_main_plan(payload)


@router.post(
    "/main/from-explorer",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_main_plan_from_explorer(
    payload: MainPlanFromExplorerCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    try:
        return await service.create_main_plan_from_explorer(payload)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/main/from-context",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_main_plan_from_context(
    payload: PlanningContextCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return await service.create_main_plan_from_context(payload)


@router.post("/{plan_id}/backup", response_model=PlanBundleRead, status_code=status.HTTP_201_CREATED)
async def create_backup_plan(
    plan_id: str,
    payload: BackupPlanCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanBundleRead:
    return await service.create_backup_plan(plan_id, payload)


def _normalize_urls(values: list[str]) -> list[str]:
    urls: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if cleaned.startswith("["):
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise ValueError("urls must be repeated form fields, comma/newline text, or a JSON array.") from exc
            if not isinstance(parsed, list):
                raise ValueError("urls JSON value must be an array.")
            urls.extend(str(item).strip() for item in parsed if str(item).strip())
            continue
        urls.extend(part.strip() for part in re.split(r"[\n,]+", cleaned) if part.strip())
    return urls


def _extract_urls(value: str) -> list[str]:
    return [
        match.rstrip(".,;:!?)]}")
        for match in re.findall(r"https?://[^\s<>\"']+", value)
    ]


def _remove_urls(value: str) -> str:
    return re.sub(r"https?://[^\s<>\"']+", " ", value).strip()


def _prepare_intake(
    raw_request: str,
    *,
    explicit_urls: list[str],
    has_images: bool = False,
) -> tuple[str, list[str]]:
    cleaned_request = raw_request.strip()
    if not cleaned_request:
        normalized_urls = list(dict.fromkeys(_normalize_urls(explicit_urls)))
        if normalized_urls:
            return "Tạo lịch trình từ URL đã cung cấp.", normalized_urls
        if has_images:
            return "Tạo lịch trình từ ảnh đính kèm.", []
        raise ValueError("Provide a travel prompt, URL, or image.")

    normalized_urls = list(
        dict.fromkeys(_normalize_urls(explicit_urls) + _extract_urls(cleaned_request))
    )
    return cleaned_request, normalized_urls


def _default_trip_spec(raw_request: str) -> ExploreTripSpecInput:
    return ExploreTripSpecInput(days=_infer_days(raw_request) or 3)


def _infer_days(raw_request: str) -> int | None:
    match = re.search(
        r"(?<!\d)(\d{1,2})\s*(?:ngày|day|days)\b",
        raw_request,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    days = int(match.group(1))
    if 1 <= days <= 30:
        return days
    return None


async def _read_and_close_images(
    images: list[UploadFile],
) -> list[ImageUploadPayload]:
    payloads: list[ImageUploadPayload] = []
    try:
        for image in images:
            payloads.append(
                ImageUploadPayload(
                    file_name=image.filename or "uploaded-image",
                    mime_type=image.content_type,
                    data=await image.read(),
                )
            )
        return payloads
    except Exception:
        for payload in payloads:
            payload.clear_data()
        raise
    finally:
        for image in images:
            await image.close()


def _parse_trip_spec(value: str | None) -> ExploreTripSpecInput | None:
    if not value:
        return None
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("tripSpec must be valid JSON.") from exc
    return ExploreTripSpecInput.model_validate(raw)


def _parse_user_state(value: str | None) -> UserPlanningState | None:
    if not value:
        return None
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("userState must be valid JSON.") from exc
    return UserPlanningState.model_validate(raw)


def _authenticated_user_state(
    state: UserPlanningState | None,
    user: User | None,
) -> UserPlanningState:
    effective = state or UserPlanningState()
    if user is None:
        return effective.model_copy(update={"user_id": None})
    return effective.model_copy(
        update={
            "user_id": str(user.id),
            "travel_preferences": LongTermPreferenceProfile.from_storage(
                user.travel_preferences
            ).explicit,
            "preference_profile": LongTermPreferenceProfile.from_storage(
                user.travel_preferences
            ),
        }
    )


def _attach_authenticated_preference(
    payload: FullExploreRequest,
    user: User | None,
) -> FullExploreRequest:
    return payload.model_copy(
        update={
            "user_state": _authenticated_user_state(payload.user_state, user)
        }
    )


def _infer_destination(raw_request: str) -> str:
    cleaned = raw_request.strip()
    day_match = re.search(r"(\d+)\s*(ngày|day|days)", cleaned, flags=re.IGNORECASE)
    destination = re.sub(
        r"^(tạo|lap|lập|make|create)\s+(cho tôi\s+)?(lịch trình|lich trinh|plan)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    if day_match:
        destination = destination.replace(day_match.group(0), "")
    destination = re.split(r",|\.|\n", destination)[0]
    destination = re.sub(r"\b(đi|di|ở|o|tại|tai|cho|trong)\b", "", destination, flags=re.IGNORECASE)
    return destination.strip()
