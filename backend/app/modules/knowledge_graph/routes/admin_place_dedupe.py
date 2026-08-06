"""Admin review API for Knowledge Graph place identity collisions."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.knowledge_graph.dependencies import get_db
from app.modules.knowledge_graph.model import KnowledgeProperty
from app.modules.users.model import User

from scripts.dedupe_knowledge_graph_places import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    _fingerprint,
    apply_report,
    load_records,
    write_report,
)


router = APIRouter(
    prefix="/admin/knowledge-graph/place-dedupe",
    tags=["admin-knowledge-graph-place-dedupe"],
)


class PlaceDedupeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PlaceDedupeRecord(PlaceDedupeResponse):
    entity_id: str = Field(alias="entityId")
    name: str
    aliases: list[str]
    place_type: str = Field(alias="placeType")
    category: str
    address: str
    region_key: str = Field(alias="regionKey")
    latitude: float
    longitude: float
    review_count: int = Field(alias="reviewCount")
    revision: int


class PlaceReviewGroup(PlaceDedupeResponse):
    group_id: str = Field(alias="groupId")
    reason_codes: list[str] = Field(alias="reasonCodes")
    records: list[PlaceDedupeRecord]


class PlaceReviewResponse(PlaceDedupeResponse):
    schema_version: int = Field(alias="schemaVersion")
    generated_at: str = Field(alias="generatedAt")
    group_count: int = Field(alias="groupCount")
    groups: list[PlaceReviewGroup]


class PlaceReviewDecisionResponse(PlaceDedupeResponse):
    group_id: str = Field(alias="groupId")
    decision: str


class ApprovePlaceMergeRequest(PlaceDedupeResponse):
    canonical_entity_id: str = Field(alias="canonicalEntityId")


def _report_path() -> Path:
    return DEFAULT_OUTPUT_DIR / "needs_review.json"


def _auto_report_path() -> Path:
    return DEFAULT_OUTPUT_DIR / "auto_merge.json"


def _read_review_report() -> dict:
    path = _report_path()
    if not path.exists():
        return {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "groupCount": 0,
            "groups": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _matches_query(group: dict, query: str) -> bool:
    normalized = " ".join(query.casefold().split())
    if not normalized:
        return True
    return any(
        normalized
        in " ".join(
            [
                str(record.get("name", "")),
                str(record.get("address", "")),
                *[str(alias) for alias in record.get("aliases", [])],
            ]
        ).casefold()
        for record in group.get("records", [])
    )


def _remove_review_group(review_report: dict, group_id: str) -> dict:
    groups = review_report.get("groups", [])
    remaining = [item for item in groups if item.get("groupId") != group_id]
    if len(remaining) == len(groups):
        from app.shared.errors import AppError

        raise AppError(404, "PLACE_REVIEW_NOT_FOUND", "Nhóm địa điểm không còn trong hàng chờ duyệt.")
    review_report.update(
        generatedAt=datetime.now(timezone.utc).isoformat(),
        groupCount=len(remaining),
        groups=remaining,
    )
    return review_report


def _review_group_ids_with_db_decisions(review_report: dict, db: Session) -> set[str]:
    groups = review_report.get("groups", [])
    entity_ids = {
        record.get("entityId")
        for group in groups
        for record in group.get("records", [])
        if record.get("entityId")
    }
    if not entity_ids:
        return set()
    properties = db.scalars(
        select(KnowledgeProperty).where(
            KnowledgeProperty.entity_id.in_(entity_ids),
            KnowledgeProperty.key.in_({"merged_into_entity_id", "dedupe_review_decisions"}),
        )
    )
    merged_entities: set[str] = set()
    dismissed_group_ids: set[str] = set()
    for prop in properties:
        if prop.key == "merged_into_entity_id":
            merged_entities.add(prop.entity_id)
            continue
        try:
            values = json.loads(prop.value)
        except (TypeError, ValueError):
            values = []
        if isinstance(values, list):
            dismissed_group_ids.update(str(value) for value in values)
    return dismissed_group_ids | {
        group.get("groupId")
        for group in groups
        if any(record.get("entityId") in merged_entities for record in group.get("records", []))
    }


def _sync_completed_review_groups(review_report: dict, db: Session) -> dict:
    completed_ids = _review_group_ids_with_db_decisions(review_report, db)
    if not completed_ids:
        return review_report
    remaining = [
        group
        for group in review_report.get("groups", [])
        if group.get("groupId") not in completed_ids
    ]
    if len(remaining) == len(review_report.get("groups", [])):
        return review_report
    review_report.update(
        generatedAt=datetime.now(timezone.utc).isoformat(),
        groupCount=len(remaining),
        groups=remaining,
    )
    write_report(_report_path(), review_report)
    return review_report


def _persist_not_merged_decision(db: Session, group_id: str, group: dict) -> None:
    # Keep the decision in the graph without changing planner eligibility.
    anchor_id = next(record["entityId"] for record in group["records"])
    prop = db.scalar(
        select(KnowledgeProperty).where(
            KnowledgeProperty.entity_id == anchor_id,
            KnowledgeProperty.key == "dedupe_review_decisions",
        )
    )
    values: list[str] = []
    if prop is not None:
        try:
            loaded = json.loads(prop.value)
            if isinstance(loaded, list):
                values = [str(value) for value in loaded]
        except (TypeError, ValueError):
            pass
    if group_id not in values:
        values.append(group_id)
    if prop is None:
        prop = KnowledgeProperty(
            entity_id=anchor_id,
            key="dedupe_review_decisions",
            value=json.dumps(values),
            source="admin:place-dedupe-review",
        )
        db.add(prop)
    else:
        prop.value = json.dumps(values)
        prop.source = "admin:place-dedupe-review"
    db.commit()


@router.get("/review", response_model=PlaceReviewResponse)
def list_place_reviews(
    _: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    query: Annotated[str, Query(max_length=200)] = "",
) -> PlaceReviewResponse:
    report = _sync_completed_review_groups(_read_review_report(), db)
    groups = [group for group in report.get("groups", []) if _matches_query(group, query)]
    return PlaceReviewResponse.model_validate(
        {
            **report,
            "groupCount": len(groups),
            "groups": groups[offset : offset + limit],
        }
    )


@router.post("/review/{group_id}/merge", response_model=PlaceReviewDecisionResponse)
def approve_place_merge(
    group_id: str,
    payload: ApprovePlaceMergeRequest,
    _: Annotated[User, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaceReviewDecisionResponse:
    # require_csrf authenticates the user; this route is restricted to admins too.
    require_role("admin")(_)
    review_report = _read_review_report()
    group = next(
        (item for item in review_report.get("groups", []) if item.get("groupId") == group_id),
        None,
    )
    if group is None:
        from app.shared.errors import AppError

        raise AppError(404, "PLACE_REVIEW_NOT_FOUND", "Nhóm địa điểm không còn trong hàng chờ duyệt.")

    record_ids = {record["entityId"] for record in group["records"]}
    if payload.canonical_entity_id not in record_ids or len(record_ids) < 2:
        from app.shared.errors import AppError

        raise AppError(422, "INVALID_PLACE_MERGE", "Địa điểm canonical không thuộc nhóm review này.")

    current_records = load_records(db)
    expected_fingerprint = review_report.get("databaseFingerprint")
    current_fingerprint = _fingerprint(current_records)
    if expected_fingerprint and expected_fingerprint != current_fingerprint:
        from app.shared.errors import AppError

        raise AppError(
            409,
            "PLACE_REVIEW_STALE",
            "Danh sách review đã thay đổi. Hãy tải lại trước khi duyệt.",
        )

    secondary_ids = sorted(record_ids - {payload.canonical_entity_id})
    auto_group = {
        "groupId": group_id,
        "canonicalEntityId": payload.canonical_entity_id,
        "secondaryEntityIds": secondary_ids,
        "confidence": "admin_reviewed",
        "reason": "admin_reviewed_needs_review",
        "records": group["records"],
        "applied": False,
    }
    apply_report(
        db,
        {
            "databaseFingerprint": current_fingerprint,
            "groups": [auto_group],
        },
        current_records,
    )

    auto_path = _auto_report_path()
    auto_report = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.exists() else {
        "schemaVersion": 1,
        "groups": [],
    }
    auto_report["groups"] = [
        *[item for item in auto_report.get("groups", []) if item.get("groupId") != group_id],
        auto_group,
    ]
    now = datetime.now(timezone.utc).isoformat()
    refreshed_fingerprint = _fingerprint(
        [record for record in current_records if record.id not in secondary_ids]
    )
    auto_report.update(
        generatedAt=now,
        databaseFingerprint=refreshed_fingerprint,
        groupCount=len(auto_report["groups"]),
        appliedGroupCount=sum(item.get("applied") is True for item in auto_report["groups"]),
        pendingGroupCount=sum(item.get("applied") is not True for item in auto_report["groups"]),
    )
    _remove_review_group(review_report, group_id)
    review_report["databaseFingerprint"] = refreshed_fingerprint
    write_report(auto_path, auto_report)
    write_report(_report_path(), review_report)
    return PlaceReviewDecisionResponse(groupId=group_id, decision="merged")


@router.post("/review/{group_id}/dismiss", response_model=PlaceReviewDecisionResponse)
def dismiss_place_merge(
    group_id: str,
    user: Annotated[User, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaceReviewDecisionResponse:
    require_role("admin")(user)
    review_report = _read_review_report()
    group = next(
        (item for item in review_report.get("groups", []) if item.get("groupId") == group_id),
        None,
    )
    if group is None:
        from app.shared.errors import AppError

        raise AppError(404, "PLACE_REVIEW_NOT_FOUND", "Nhóm địa điểm không còn trong hàng chờ duyệt.")
    _persist_not_merged_decision(db, group_id, group)
    review_report = _remove_review_group(review_report, group_id)
    write_report(_report_path(), review_report)
    return PlaceReviewDecisionResponse(groupId=group_id, decision="not_merged")
