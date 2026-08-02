import json
import re
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.modules.auth.dependencies import get_optional_current_user
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.plans.dependencies import (
    get_current_location_route_service,
    get_destination_discovery_service,
    get_plan_mutation_service,
    get_plan_service,
)
from app.modules.plans.discovery.schema import (
    DestinationDiscoveryRequest,
    DestinationDiscoveryResponse,
)
from app.modules.plans.discovery.service import DestinationDiscoveryService
from app.modules.plans.domain.entities import PlanTransportLeg
from app.modules.plans.dto.agent_contracts import UserPlanningState
from app.modules.plans.explorer.schema import (
    ExploreIntakeResponse,
    ExploreTripSpecInput,
    FullExploreRequest,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    MutationResponse,
    PlaceSuggestion,
    ReorderItemsRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.schema import (
    BackupPlanCreate,
    CurrentLocationRouteCreate,
    DayDirectionsCreate,
    FeatureMapItem,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanGenerationRead,
    PlanBundleRead,
    PlanRead,
    PlanningContextCreate,
)
from app.modules.plans.routing.current_location_service import (
    CurrentLocationRouteService,
)
from app.modules.plans.routing.optimizer import RouteUnavailableError
from app.modules.plans.service import PlanService
from app.modules.users.model import User

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/feature-map", response_model=list[FeatureMapItem])
def feature_map(service: Annotated[PlanService, Depends(get_plan_service)]) -> list[FeatureMapItem]:
    return service.feature_map()


@router.post(
    "/destinations/discover",
    response_model=DestinationDiscoveryResponse,
)
def discover_destinations(
    payload: DestinationDiscoveryRequest,
    service: Annotated[
        DestinationDiscoveryService,
        Depends(get_destination_discovery_service),
    ],
) -> DestinationDiscoveryResponse:
    return service.discover(payload)




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
    force_refresh: Annotated[bool, Form(alias="forceRefresh")] = False,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> ExploreIntakeResponse:
    try:
        effective_request, normalized_urls = _prepare_intake(
            raw_request,
            explicit_urls=urls or [],
            has_images=bool(images),
        )
        normalized_destination = (
            destination
            or _infer_destination(_remove_urls(effective_request))
            or _infer_destination_from_urls(normalized_urls)
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
            force_url_refresh=force_refresh,
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
    response_model=PlanGenerationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_main_plan_from_explorer(
    payload: MainPlanFromExplorerCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanGenerationRead:
    try:
        plan, timing_report = (
            await service.create_main_plan_from_explorer_with_timing(payload)
        )
        return PlanGenerationRead(plan=plan, timingReport=timing_report)
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


@router.post(
    "/current-location-route",
    response_model=PlanTransportLeg,
)
def current_location_route(
    payload: CurrentLocationRouteCreate,
    service: Annotated[
        CurrentLocationRouteService,
        Depends(get_current_location_route_service),
    ],
) -> PlanTransportLeg:
    return service.calculate(payload)


@router.post(
    "/day-directions",
    response_model=list[PlanTransportLeg],
)
def day_directions(
    payload: DayDirectionsCreate,
    service: Annotated[
        CurrentLocationRouteService,
        Depends(get_current_location_route_service),
    ],
) -> list[PlanTransportLeg]:
    try:
        return service.calculate_day(payload)
    except RouteUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/{plan_id}/backup", response_model=PlanBundleRead, status_code=status.HTTP_201_CREATED)
async def create_backup_plan(
    plan_id: str,
    payload: BackupPlanCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanBundleRead:
    return await service.create_backup_plan(plan_id, payload)


@router.get("/places/search", response_model=list[PlaceSuggestion])
async def search_places(
    query: Annotated[str, Query(min_length=2, max_length=100)],
    destination: Annotated[str | None, Query()] = None,
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)] = None,
) -> list[PlaceSuggestion]:
    return await mutation_service.search_place_suggestions(query, destination)


@router.post("/{plan_id}/items", response_model=MutationResponse, status_code=status.HTTP_201_CREATED)
async def add_plan_item(
    plan_id: str,
    payload: AddItemRequest,
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
) -> MutationResponse:
    plan = plan_service.repository.get(plan_id)
    result = await mutation_service.add_item(plan, payload)
    plan_service.repository.save(result.plan)
    return result


@router.patch("/{plan_id}/days/{day}/items/{item_id}", response_model=MutationResponse)
async def update_plan_item(
    plan_id: str,
    day: int,
    item_id: str,
    payload: UpdateItemRequest,
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
) -> MutationResponse:
    plan = plan_service.repository.get(plan_id)
    result = await mutation_service.update_item(plan, day, item_id, payload)
    plan_service.repository.save(result.plan)
    return result


@router.delete("/{plan_id}/days/{day}/items/{item_id}", response_model=MutationResponse)
def remove_plan_item(
    plan_id: str,
    day: int,
    item_id: str,
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
) -> MutationResponse:
    plan = plan_service.repository.get(plan_id)
    result = mutation_service.remove_item(plan, day, item_id)
    plan_service.repository.save(result.plan)
    return result


@router.post("/{plan_id}/days/{day}/items/{item_id}/move", response_model=MutationResponse)
def move_plan_item(
    plan_id: str,
    day: int,
    item_id: str,
    payload: MoveItemRequest,
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
) -> MutationResponse:
    plan = plan_service.repository.get(plan_id)
    result = mutation_service.move_item(plan, day, item_id, payload)
    plan_service.repository.save(result.plan)
    return result


@router.put("/{plan_id}/days/{day}/items/reorder", response_model=MutationResponse)
def reorder_plan_items(
    plan_id: str,
    day: int,
    payload: ReorderItemsRequest,
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
    mutation_service: Annotated[PlanMutationService, Depends(get_plan_mutation_service)],
) -> MutationResponse:
    plan = plan_service.repository.get(plan_id)
    result = mutation_service.reorder_items(plan, day, payload)
    plan_service.repository.save(result.plan)
    return result



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
    # Keep a missing duration distinct from an explicit request. The planning
    # service applies the three-day product default while still expanding it
    # when URL/OCR evidence needs more days.
    return ExploreTripSpecInput(days=_infer_days(raw_request))


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


def _infer_destination_from_urls(urls: list[str]) -> str:
    for url in urls:
        query = parse_qs(urlsplit(url).query)
        for value in query.get("q", []):
            match = re.search(
                r"(?:what\s+to\s+do|things\s+to\s+do)\s+in\s+(.+?)(?:[?!]|$)",
                value,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1).strip().title()
    return ""
