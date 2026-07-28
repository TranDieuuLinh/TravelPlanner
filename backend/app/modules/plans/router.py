import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.explorer.schema import ExploreResponse, ExploreTripSpecInput, FullExploreRequest
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.schema import (
    BackupPlanCreate,
    FeatureMapItem,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanBundleRead,
    PlanRead,
)
from app.modules.plans.service import PlanService

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/feature-map", response_model=list[FeatureMapItem])
def feature_map(service: Annotated[PlanService, Depends(get_plan_service)]) -> list[FeatureMapItem]:
    return service.feature_map()




@router.post("/explore/full", response_model=ExploreResponse)
async def explore_full(payload: FullExploreRequest, service: Annotated[PlanService, Depends(get_plan_service)]) -> ExploreResponse:
    try:
        return await service.explore_full(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/explore/full/intake", response_model=ExploreResponse)
async def explore_full_intake(
    raw_request: Annotated[str, Form(alias="rawRequest")],
    service: Annotated[PlanService, Depends(get_plan_service)],
    destination: Annotated[str | None, Form()] = None,
    urls: Annotated[list[str] | None, Form()] = None,
    trip_spec_json: Annotated[str | None, Form(alias="tripSpec")] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> ExploreResponse:
    try:
        effective_request, normalized_urls = _prepare_intake(
            raw_request,
            explicit_urls=urls or [],
        )
        normalized_destination = (
            destination or _infer_destination(_remove_urls(effective_request))
        ).strip()
        trip_spec = _parse_trip_spec(trip_spec_json)
        uploaded_images = await _read_and_close_images(images or [])
        return await service.explore_from_intake(
            raw_request=effective_request,
            destination=normalized_destination or "unspecified",
            urls=normalized_urls,
            images=uploaded_images,
            trip_spec=trip_spec,
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
    return await service.create_main_plan_from_explorer(payload)


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
) -> tuple[str, list[str]]:
    cleaned_request = raw_request.strip()
    if not cleaned_request:
        raise ValueError(
            "Provide a travel prompt or URL before attaching optional images."
        )

    normalized_urls = list(
        dict.fromkeys(_normalize_urls(explicit_urls) + _extract_urls(cleaned_request))
    )
    return cleaned_request, normalized_urls


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
