from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeGraphImport,
    KnowledgeGraphImportEdge,
    KnowledgeGraphImportNode,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.repositories.kg_repository import KnowledgeGraphRepository
from app.modules.places.category import canonical_place_category
from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import SourceDocument
from app.modules.plans.explorer.place_policy import (
    concise_source_activity,
    is_schedulable_place,
)
from app.modules.plans.domain.plan_notes import (
    compose_plan_source_note,
    source_note_provenance,
)
from app.modules.plans.explorer.schema import (
    PlaceCandidateReview,
    PlaceMatchOption,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)
from app.modules.plans.explorer.tools.url_reels.utils import (
    canonicalize_url,
    detect_platform,
    extract_youtube_video_id,
)
from app.modules.plans.schema import SelectedPlaceCreate
from app.modules.plans.trip_theme_planner.region_context import normalize_region_key


URL_EXTRACTION_CACHE_VERSION = 6


@dataclass(frozen=True)
class SourceArtifactView:
    source_url: str
    platform: str
    artifact_type: str
    content_text: str
    language: str
    source: str
    metadata_json: dict
    fetched_at: datetime


def _artifact_source_url(url: str, platform: str | None = None) -> str:
    detected_platform = platform or detect_platform(url)
    video_id = extract_youtube_video_id(url)
    if detected_platform == "youtube" and video_id is not None:
        return f"https://www.youtube.com/watch?v={video_id}"
    return canonicalize_url(url)


class ExplorerPersistenceRepository:
    """Persist Explorer output as source documents and reviewable KG proposals."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        *,
        intake_id: str,
        user_id: str | None,
        destination: str,
        resolutions: list[PlaceResolution],
        candidate_reviews: list[PlaceCandidateReview] | None = None,
        url_results: list[UrlReelExtractionResult] | None = None,
    ) -> None:
        documents = self._save_source_documents(url_results or [])
        numeric_user_id = _numeric_user_id(user_id)
        import_job = KnowledgeGraphImport(
            id=intake_id,
            import_kind="explorer_intake",
            source_label=destination,
            source_url=next(iter(documents), None),
            source_document_id=(
                next(iter(documents.values())).id if documents else None
            ),
            source_content="",
            processing_status="succeeded",
            review_status="not_required",
            status="succeeded",
            schema_version="explorer-place-proposal-v1",
            ontology_version="knowledge-graph-v2",
            dataset_hash="",
            created_by=numeric_user_id,
            destination=destination,
            candidate_reviews=[
                review.model_dump(mode="json", by_alias=True)
                for review in (candidate_reviews or [])
            ],
        )
        self.session.add(import_job)
        self.session.flush()

        area_matches, area_entity, area_identity_status = self._match_knowledge_entities(
            destination,
            aliases=[destination],
            expected_type="Area",
            region=destination,
        )
        area_temp_id = "area-root"
        area_node = KnowledgeGraphImportNode(
            import_id=intake_id,
            temp_id=area_temp_id,
            entity_id=(
                area_entity.id if area_entity is not None
                else f"area_{hashlib.sha1(_normalized(destination).encode()).hexdigest()[:20]}"
            ),
            type=area_entity.entity_type if area_entity is not None else "Area",
            canonical_name=destination,
            aliases=[destination],
            properties={},
            evidence=[],
            confidence=1.0,
            match_status="existing" if area_entity is not None else "new",
            match_candidates=area_matches,
            selected_entity_id=area_entity.id if area_entity is not None else None,
            identity_status=area_identity_status,
            selection_method="knowledge_top_k" if area_entity is not None else None,
            candidate_key=f"area:{_slug(destination)}",
            candidate_name=destination,
            search_region=destination,
            source_evidence={},
            provider="knowledge_graph" if area_entity is not None else None,
            provider_snapshot={},
            preference_level="mentioned",
            decision="pending",
            validation_issues=[], required_properties=[], optional_properties=[],
        )
        self.session.add(area_node)
        persisted_count = 1
        persisted_edges = 0
        for resolution in resolutions:
            if not _is_persistable_resolution(resolution, destination=destination):
                continue
            candidate = resolution.candidate
            source_url = _candidate_source_url(candidate)
            document = documents.get(_artifact_source_url(source_url)) if source_url else None
            matches, matched_entity, identity_status = self._match_knowledge_entities(
                resolution.name,
                aliases=[candidate.name, *candidate.search_names],
                expected_type=_knowledge_entity_type(resolution.place_type),
                region=candidate.search_region or destination,
            )
            provider_snapshot = _provider_snapshot(resolution)
            candidate_key = _shared_candidate_key(candidate, destination)
            venue_temp_id = f"place-{uuid4().hex[:20]}"
            node = KnowledgeGraphImportNode(
                import_id=intake_id,
                temp_id=venue_temp_id,
                entity_id=(
                    matched_entity.id
                    if matched_entity is not None
                    else f"place_{hashlib.sha1(candidate_key.encode()).hexdigest()[:20]}"
                ),
                type=_knowledge_entity_type(resolution.place_type),
                canonical_name=resolution.name,
                aliases=list(dict.fromkeys([candidate.name, *candidate.search_names])),
                properties={},
                evidence=list(dict.fromkeys(candidate.source_evidence.values())),
                confidence=float(candidate.confidence),
                match_status="existing" if matched_entity is not None else "new",
                match_candidates=matches,
                selected_entity_id=(matched_entity.id if matched_entity is not None else None),
                identity_status=identity_status,
                selection_method=("knowledge_top_k" if matched_entity is not None else None),
                candidate_key=candidate_key,
                candidate_name=candidate.name,
                search_region=candidate.search_region or destination,
                source_evidence=dict(candidate.source_evidence),
                provider=resolution.provider,
                provider_external_id=resolution.external_id,
                provider_snapshot=provider_snapshot,
                source_order=candidate.source_order,
                source_day=candidate.source_day,
                source_time_hint=candidate.source_time_hint,
                source_activity=concise_source_activity(candidate.source_activity),
                source_duration_minutes=candidate.source_duration_minutes,
                preference_level=candidate.preference_level.value,
                attributes=list(candidate.attributes),
                decision="pending",
                validation_issues=[],
                required_properties=[],
                optional_properties=[],
                source_document_id=document.id if document is not None else None,
            )
            self.session.add(node)
            self.session.add(KnowledgeGraphImportEdge(
                import_id=intake_id,
                temp_id=f"located-in-{uuid4().hex[:16]}",
                from_ref=venue_temp_id,
                relationship_type="LOCATED_IN",
                to_ref=area_temp_id,
                recommendations=[],
                source=source_url or f"explorer:{intake_id}",
                evidence=list(dict.fromkeys(candidate.source_evidence.values())),
                confidence=float(candidate.confidence),
                match_status="new",
                decision="pending",
                validation_issues=[],
            ))
            persisted_count += 1
            persisted_edges += 1
        import_job.node_count = persisted_count
        import_job.edge_count = persisted_edges
        if persisted_count:
            import_job.review_status = "pending" if any(
                node.selected_entity_id is None for node in import_job.nodes
            ) else "not_required"
        self.session.commit()

    def load_candidate_reviews(self, intake_id: str | None) -> list[PlaceCandidateReview]:
        if intake_id is None:
            return []
        row = self.session.get(KnowledgeGraphImport, intake_id)
        if row is None or row.import_kind != "explorer_intake":
            return []
        return [
            PlaceCandidateReview.model_validate(value)
            for value in (row.candidate_reviews or [])
        ]

    def replace_candidate_reviews(
        self,
        intake_id: str,
        reviews: list[PlaceCandidateReview],
    ) -> None:
        row = self.session.get(KnowledgeGraphImport, intake_id)
        if row is None or row.import_kind != "explorer_intake":
            return
        row.candidate_reviews = [
            review.model_dump(mode="json", by_alias=True) for review in reviews
        ]

    def load_must_places(
        self,
        intake_id: str,
        user_id: str | None,
    ) -> list[SelectedPlaceCreate]:
        import_job = self.session.get(KnowledgeGraphImport, intake_id)
        if (
            import_job is None
            or import_job.import_kind != "explorer_intake"
            or import_job.created_by != _numeric_user_id(user_id)
        ):
            return []
        nodes = list(self.session.scalars(
            select(KnowledgeGraphImportNode)
            .where(KnowledgeGraphImportNode.import_id == intake_id)
            .order_by(KnowledgeGraphImportNode.source_order, KnowledgeGraphImportNode.id)
        ))
        anchor_coordinates = [
            (
                _optional_float((item.provider_snapshot or {}).get("latitude")),
                _optional_float((item.provider_snapshot or {}).get("longitude")),
            )
            for item in nodes
            if item.identity_status != "branch_ambiguous"
            and _optional_float((item.provider_snapshot or {}).get("latitude")) is not None
            and _optional_float((item.provider_snapshot or {}).get("longitude")) is not None
        ]
        output: list[SelectedPlaceCreate] = []
        for node in nodes:
            snapshot = dict(node.provider_snapshot or {})
            route_selection = _select_branch_near_route(
                node.match_candidates or [],
                anchors=anchor_coordinates,
            ) if node.identity_status == "branch_ambiguous" else None
            if route_selection is not None:
                snapshot.update({
                    "name": route_selection.get("canonicalName") or snapshot.get("name"),
                    "address": route_selection.get("address") or snapshot.get("address"),
                    "latitude": route_selection.get("latitude"),
                    "longitude": route_selection.get("longitude"),
                })
            if not _is_schedulable_snapshot(node, snapshot, import_job.destination or ""):
                continue
            source_refs = [
                document.canonical_url
                for document in [
                    self.session.get(SourceDocument, node.source_document_id)
                    if node.source_document_id else None
                ]
                if document is not None
            ]
            provider_description = _optional_text(snapshot.get("description"))
            source_note = compose_plan_source_note(
                source_activity=node.source_activity,
                source_evidence=dict(node.source_evidence or {}),
                provider_description=provider_description,
            )
            note_sources = source_note_provenance(
                source_refs=source_refs,
                evidence_types=list((node.source_evidence or {}).keys()),
                provider=node.provider,
                provider_ref=(
                    _optional_text(snapshot.get("googleMapsUrl"))
                    or _optional_text(snapshot.get("externalId"))
                ),
                provider_fetched_at=snapshot.get("fetchedAt"),
                include_provider=bool(provider_description),
            )
            output.append(
                SelectedPlaceCreate(
                    name=str(snapshot.get("name") or node.canonical_name),
                    placeId=(
                        route_selection.get("entityId") if route_selection is not None
                        else node.selected_entity_id
                    ),
                    address=snapshot.get("address"),
                    priority=_priority_from_confidence(node.confidence),
                    mustVisit=node.preference_level == "must_visit",
                    preferenceLevel=node.preference_level,
                    regionKey=(
                        snapshot.get("regionKey")
                        or normalize_region_key(
                            str(snapshot.get("city") or import_job.destination or "")
                        )
                    ),
                    tags=list(dict.fromkeys([
                        canonical_place_category(snapshot.get("placeType")),
                        *(node.attributes or []),
                    ])),
                    latitude=snapshot.get("latitude"),
                    longitude=snapshot.get("longitude"),
                    sourceRefs=source_refs,
                    sourceProvider=node.provider,
                    sourceImportNodeId=node.id,
                    candidateEntityIds=[
                        str(candidate_match["entityId"])
                        for candidate_match in (node.match_candidates or [])
                        if candidate_match.get("entityId")
                    ],
                    selectionMethod=(
                        "route_proximity" if route_selection is not None
                        else node.selection_method
                    ),
                    routeScore=(
                        route_selection.get("routeScore")
                        if route_selection is not None else None
                    ),
                    identityConfidence=(
                        "high" if node.identity_status == "resolved"
                        else "low" if node.identity_status == "branch_ambiguous"
                        else "medium"
                    ),
                    notes=source_note,
                    noteSources=note_sources,
                    imageUrls=_image_urls_from_snapshot(snapshot),
                    rating=snapshot.get("rating"),
                    reviewCount=snapshot.get("reviewCount"),
                    sourceOrder=node.source_order,
                    sourceDay=node.source_day,
                    sourceTimeHint=node.source_time_hint,
                    sourceActivity=node.source_activity,
                    sourceDurationMinutes=node.source_duration_minutes,
                )
            )
        return output

    def load_cached_url_result(self, url: str) -> UrlReelExtractionResult | None:
        source_url = _artifact_source_url(url)
        document = self.session.scalar(
            select(SourceDocument).where(SourceDocument.canonical_url == source_url)
        )
        if document is None:
            return None
        payload = dict(document.extracted_context_json or {})
        if payload.get("_cacheVersion") != URL_EXTRACTION_CACHE_VERSION:
            return None
        context = ExtractedContext.model_validate(payload)
        return UrlReelExtractionResult(
            url=source_url,
            platform=document.platform,
            metadata=UrlMetadata(
                originalUrl=url,
                canonicalUrl=source_url,
                platform=document.platform,
            ),
            artifacts=MediaArtifacts(),
            speechToText=SpeechToTextResult(
                text="",
                status="cached",
                source="shared_source_document",
                durationSeconds=0,
            ),
            extractedContext=context,
            timings={"sharedSourceDocument": 0.0},
        )

    def delete_url_cache(self, url: str) -> bool:
        """Delete the shared URL extraction/resolution cache for one URL.

        Historical Explorer imports remain intact, but their link to the
        shared source document is cleared so a replay cannot reuse an old
        provider snapshot. Canonical KG entities are never deleted here.
        """
        source_url = _artifact_source_url(url)
        document = self.session.scalar(
            select(SourceDocument).where(SourceDocument.canonical_url == source_url)
        )
        if document is None:
            return False
        self.session.execute(
            update(KnowledgeGraphImportNode)
            .where(KnowledgeGraphImportNode.source_document_id == document.id)
            .values(source_document_id=None)
        )
        self.session.delete(document)
        self.session.commit()
        return True

    def load_url_source_artifacts(
        self,
        url: str,
        *,
        artifact_types: set[str] | None = None,
    ) -> list[SourceArtifactView]:
        source_url = _artifact_source_url(url)
        document = self.session.scalar(
            select(SourceDocument).where(SourceDocument.canonical_url == source_url)
        )
        if document is None:
            return []
        output: list[SourceArtifactView] = []
        for artifact_type, by_language in (document.artifacts_json or {}).items():
            if artifact_types and artifact_type not in artifact_types:
                continue
            for language, artifact in (by_language or {}).items():
                output.append(SourceArtifactView(
                    source_url=source_url,
                    platform=document.platform,
                    artifact_type=artifact_type,
                    content_text=str(artifact.get("text") or ""),
                    language="" if language == "_" else language,
                    source=str(artifact.get("source") or artifact_type),
                    metadata_json=dict(artifact.get("metadata") or {}),
                    fetched_at=document.fetched_at,
                ))
        return output

    def find_cached_resolution(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution | None:
        source_url = _candidate_source_url(candidate)
        if source_url is None:
            return None
        document = self.session.scalar(
            select(SourceDocument).where(
                SourceDocument.canonical_url == _artifact_source_url(source_url)
            )
        )
        if document is None:
            return None
        rows = list(self.session.scalars(
            select(KnowledgeGraphImportNode).where(
                KnowledgeGraphImportNode.source_document_id == document.id
            )
        ))
        candidate_key = _shared_candidate_key(candidate, destination)
        normalized_name = _slug(candidate.name)
        row = next((
            item for item in rows
            if item.candidate_key == candidate_key
            or _slug(item.candidate_name or "") == normalized_name
        ), None)
        if row is None or not row.provider_snapshot:
            return None
        payload = dict(row.provider_snapshot)
        payload["candidate"] = candidate.model_dump(mode="json", by_alias=True)
        return PlaceResolution.model_validate(payload)

    def resolve_from_knowledge_graph(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution | None:
        """Resolve from canonical entities/aliases before any provider lookup."""
        matches, selected, identity_status = self._match_knowledge_entities(
            candidate.name,
            aliases=[candidate.name, *candidate.search_names],
            expected_type=_knowledge_entity_type(candidate.category.value),
            region=candidate.search_region or destination,
        )
        if not matches or identity_status not in {"resolved", "branch_ambiguous"}:
            return None
        chosen = matches[0]
        if identity_status == "branch_ambiguous":
            coordinates = [
                (item.get("latitude"), item.get("longitude"))
                for item in matches
                if item.get("latitude") is not None and item.get("longitude") is not None
            ]
            if not coordinates:
                return None
            latitude = sum(item[0] for item in coordinates) / len(coordinates)
            longitude = sum(item[1] for item in coordinates) / len(coordinates)
        else:
            latitude = chosen.get("latitude")
            longitude = chosen.get("longitude")
            if latitude is None or longitude is None:
                return None
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            resolutionReason=(
                "branch_ambiguous" if identity_status == "branch_ambiguous" else None
            ),
            provider="knowledge_graph",
            placeId=selected.id if selected is not None else None,
            name=selected.canonical_name if selected is not None else candidate.name,
            placeType=chosen.get("type"),
            address=chosen.get("address"),
            city=candidate.search_region or destination,
            latitude=latitude,
            longitude=longitude,
            matchOptions=[
                PlaceMatchOption(
                    rank=index,
                    matchSource="knowledge_graph",
                    provider="knowledge_graph",
                    placeId=item.get("entityId"),
                    name=str(item.get("canonicalName") or candidate.name),
                    selected=(
                        selected is not None and item.get("entityId") == selected.id
                    ),
                    address=item.get("address"),
                    latitude=item.get("latitude"),
                    longitude=item.get("longitude"),
                    score=float(item.get("score") or 0),
                    scoreComponents={"knowledgeGraph": float(item.get("score") or 0)},
                )
                for index, item in enumerate(matches, start=1)
            ],
            dataConfidence="high" if selected is not None else "medium",
            fetchedAt=datetime.now(timezone.utc),
        )

    def _save_source_documents(
        self,
        results: list[UrlReelExtractionResult],
    ) -> dict[str, SourceDocument]:
        documents: dict[str, SourceDocument] = {}
        for result in results:
            source_url = _artifact_source_url(
                result.metadata.canonical_url or result.url,
                result.platform,
            )
            row = self.session.scalar(
                select(SourceDocument).where(SourceDocument.canonical_url == source_url)
            )
            if row is None:
                row = SourceDocument(
                    id=str(uuid4()),
                    canonical_url=source_url,
                    platform=result.platform,
                    artifacts_json={},
                    extracted_context_json={},
                )
                self.session.add(row)
            artifacts = dict(row.artifacts_json or {})
            speech = result.speech_to_text
            if speech.status == "ok" and speech.text.strip():
                artifact_type = (
                    "webpage" if speech.source == "web_page_text"
                    else "caption" if speech.source.startswith("youtube_captions")
                    else "stt"
                )
                text = (
                    "\n".join(
                        observation.evidence.strip()
                        for observation in speech.observations
                        if observation.evidence.strip()
                    )
                    if artifact_type == "webpage" else speech.text.strip()
                )
                if text:
                    by_language = dict(artifacts.get(artifact_type) or {})
                    by_language[speech.language or "_"] = {
                        "text": text,
                        "source": speech.source or artifact_type,
                        "metadata": {
                            "observations": [
                                item.model_dump(mode="json", by_alias=True)
                                for item in speech.observations
                            ],
                            "audioDurationSeconds": speech.audio_duration_seconds,
                            "chunkCount": speech.chunk_count,
                        },
                    }
                    artifacts[artifact_type] = by_language
            vision = result.frame_vision
            if vision.status in {"ok", "partial"} and vision.text.strip():
                artifacts["ocr"] = {
                    "_": {
                        "text": vision.text.strip(),
                        "source": "frame_vision",
                        "metadata": {
                            "places": list(vision.places),
                            "observations": [
                                item.model_dump(mode="json", by_alias=True)
                                for item in vision.observations
                            ],
                        },
                    }
                }
            extracted_context = result.extracted_context.model_dump(
                mode="json", by_alias=True
            )
            extracted_context["_cacheVersion"] = URL_EXTRACTION_CACHE_VERSION
            row.platform = result.platform
            row.artifacts_json = artifacts
            row.extracted_context_json = extracted_context
            row.extractor_version = str(URL_EXTRACTION_CACHE_VERSION)
            row.artifact_hash = _artifact_hash(artifacts)
            row.fetched_at = datetime.now(timezone.utc)
            self.session.flush()
            documents[source_url] = row
        return documents

    def _match_knowledge_entities(
        self,
        name: str,
        *,
        aliases: list[str],
        expected_type: str,
        region: str,
        top_k: int = 5,
    ) -> tuple[list[dict], KnowledgeEntity | None, str]:
        """Rank canonical names and reviewed aliases without requiring exact text.

        Same-name branches deliberately remain unresolved here. Their candidate
        entity IDs travel with the plan input so route selection can pick a
        branch without another Google lookup.
        """
        observed = list(dict.fromkeys(
            value.strip() for value in [name, *aliases] if value and value.strip()
        ))
        repository = KnowledgeGraphRepository(self.session)
        candidate_by_id: dict[str, KnowledgeEntity] = {}
        for observed_name in observed:
            exact = repository.find_exact_name_match(observed_name)
            if exact is not None:
                candidate_by_id[exact.id] = exact
            exact_alias = repository.find_exact_alias_match(observed_name)
            if exact_alias is not None:
                alias_entity = self.session.get(KnowledgeEntity, exact_alias.entity_id)
                if alias_entity is not None:
                    candidate_by_id[alias_entity.id] = alias_entity
            for entity in repository.find_fuzzy_entity_candidates(
                observed_name,
                limit=top_k,
                entity_types=_compatible_entity_types(expected_type),
            ):
                candidate_by_id[entity.id] = entity

        properties_by_entity: dict[str, dict[str, str]] = {}
        if candidate_by_id:
            property_rows = self.session.scalars(
                select(KnowledgeProperty).where(
                    KnowledgeProperty.entity_id.in_(list(candidate_by_id))
                )
            )
            for prop in property_rows:
                properties_by_entity.setdefault(prop.entity_id, {})[prop.key] = prop.value

        ranked: list[tuple[float, float, KnowledgeEntity, list[str], dict[str, str]]] = []
        normalized_region = _normalized(region)
        for entity in candidate_by_id.values():
            if entity.status not in {"verified", "active"}:
                continue
            approved_aliases = [
                alias.alias for alias in entity.aliases
                if alias.status in {"imported", "verified", "active", "approved"}
            ]
            entity_names = [entity.canonical_name, *approved_aliases]
            name_score = max(
                SequenceMatcher(None, _normalized(source_name), _normalized(entity_name)).ratio()
                for source_name in observed
                for entity_name in entity_names
            )
            type_score = 1.0 if entity.entity_type in _compatible_entity_types(expected_type) else 0.0
            properties = properties_by_entity.get(entity.id, {})
            location_text = " ".join(
                str(properties.get(key) or "")
                for key in ("address", "city", "area", "primary_area", "region_key")
            )
            region_score = (
                1.0 if normalized_region and normalized_region in _normalized(location_text)
                else 0.0
            )
            score = 0.85 * name_score + 0.10 * type_score + 0.05 * region_score
            rules = ["name_or_alias"]
            if type_score:
                rules.append("entity_type")
            if region_score:
                rules.append("region")
            ranked.append((score, name_score, entity, rules, properties))
        ranked.sort(key=lambda item: (-item[0], item[2].canonical_name, item[2].id))
        ranked = ranked[:top_k]
        matches = [
            {
                "entityId": entity.id,
                "canonicalName": entity.canonical_name,
                "type": entity.entity_type,
                "score": round(score, 4),
                "matchedRules": rules,
                "latitude": _optional_float(properties.get("latitude")),
                "longitude": _optional_float(properties.get("longitude")),
                "address": properties.get("address"),
            }
            for score, _name_score, entity, rules, properties in ranked
        ]
        if not ranked or ranked[0][0] < 0.82:
            return matches, None, "unresolved"

        top_score, top_name_score, top_entity, _rules, _properties = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        same_name_branches = bool(
            runner_up
            and top_name_score >= 0.9
            and runner_up[1] >= 0.9
            and (
                _normalized(top_entity.canonical_name)
                == _normalized(runner_up[2].canonical_name)
                or top_score - runner_up[0] < 0.08
            )
        )
        if same_name_branches:
            return matches, None, "branch_ambiguous"
        if runner_up is not None and top_score - runner_up[0] < 0.08:
            return matches, None, "ambiguous"
        return matches, top_entity, "resolved"


def _candidate_source_url(candidate: UnifiedPlaceCandidate) -> str | None:
    source_url = next((source.url for source in candidate.sources if source.url), None)
    return canonicalize_url(source_url) if source_url else None


def _shared_candidate_key(candidate: UnifiedPlaceCandidate, destination: str) -> str:
    return _slug(candidate.name) if _candidate_source_url(candidate) else (
        f"{_slug(destination)}:{_slug(candidate.name)}"
    )


def _is_persistable_resolution(
    resolution: PlaceResolution,
    *,
    destination: str,
) -> bool:
    if resolution.status != "resolved":
        return False
    return is_schedulable_place(
        is_url_source=any(
            source.type.value == "url" and source.url
            for source in resolution.candidate.sources
        ),
        resolution_status=resolution.status,
        latitude=resolution.latitude,
        longitude=resolution.longitude,
        candidate_name=resolution.candidate.name,
        resolved_name=resolution.name,
        city=resolution.city,
        destination=destination,
        country=resolution.country,
    )


def _is_schedulable_snapshot(
    node: KnowledgeGraphImportNode,
    snapshot: dict,
    destination: str,
) -> bool:
    return is_schedulable_place(
        is_url_source=bool(node.source_document_id),
        resolution_status=str(snapshot.get("status") or "resolved"),
        latitude=snapshot.get("latitude"),
        longitude=snapshot.get("longitude"),
        candidate_name=node.candidate_name or node.canonical_name,
        resolved_name=str(snapshot.get("name") or node.canonical_name),
        city=snapshot.get("city"),
        destination=destination,
        country=snapshot.get("country"),
    )


def _knowledge_entity_type(place_type: str | None) -> str:
    category = canonical_place_category(place_type)
    if category in {"food", "restaurant"}:
        return "Restaurant"
    if category in {"cafe", "drink_dessert"}:
        return "DrinkDessert"
    if category in {"hotel", "accommodation"}:
        return "Accommodation"
    return "TravelPlace"


def _compatible_entity_types(expected_type: str) -> set[str]:
    aliases = {
        "Area": {"Area", "AreaAdm0", "AreaAdm1", "AreaAdm2"},
        "Restaurant": {"Restaurant", "TravelPlace", "Place"},
        "DrinkDessert": {"DrinkDessert", "Cafe", "TravelPlace", "Place"},
        "Accommodation": {"Accommodation", "Hotel", "TravelPlace", "Place"},
        "TravelPlace": {
            "TravelPlace", "Place", "Attraction", "Shop", "Entertainment",
            "Restaurant", "DrinkDessert", "Accommodation",
        },
    }
    return aliases.get(expected_type, {expected_type})


def _provider_snapshot(resolution: PlaceResolution) -> dict:
    image_urls = _image_urls_from_snapshot(
        {"placeMetadata": resolution.place_metadata}
    )
    return {
        "status": resolution.status,
        "externalId": resolution.external_id,
        "name": resolution.name,
        "placeType": resolution.place_type,
        "address": resolution.address,
        "city": resolution.city,
        "description": resolution.description,
        "latitude": float(resolution.latitude) if resolution.latitude is not None else None,
        "longitude": float(resolution.longitude) if resolution.longitude is not None else None,
        "googleMapsUrl": resolution.source_link,
        "imageUrl": image_urls[0] if image_urls else None,
        "openingHours": resolution.opening_hours,
        "rating": float(resolution.rating) if resolution.rating is not None else None,
        "reviewCount": resolution.review_count,
        "fetchedAt": resolution.fetched_at.isoformat() if resolution.fetched_at else None,
        "attribution": resolution.attribution,
    }


def _image_urls_from_snapshot(snapshot: object) -> list[str]:
    if not isinstance(snapshot, dict):
        return []
    metadata = snapshot.get("placeMetadata")
    if not isinstance(metadata, dict):
        metadata = {}
    values: list[object] = []
    if snapshot.get("imageUrl"):
        values.append(snapshot["imageUrl"])
    for key in ("imageUrl", "photoUrl", "thumbnailUrl"):
        if metadata.get(key):
            values.append(metadata[key])
    for key in ("imageUrls", "images"):
        value = metadata.get(key)
        if isinstance(value, list):
            values.extend(value)
    urls: list[str] = []
    for value in values:
        candidate = value.get("url") if isinstance(value, dict) else value
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            if candidate not in urls:
                urls.append(candidate)
    return urls[:1]


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _select_branch_near_route(
    candidates: list[dict],
    *,
    anchors: list[tuple[float, float]],
) -> dict | None:
    with_coordinates = [
        item for item in candidates
        if _optional_float(item.get("latitude")) is not None
        and _optional_float(item.get("longitude")) is not None
    ]
    if not with_coordinates:
        return None

    def route_cost(item: dict) -> float:
        if not anchors:
            return 0.0
        latitude = float(item["latitude"])
        longitude = float(item["longitude"])
        return sum(
            (latitude - anchor_latitude) ** 2
            + (longitude - anchor_longitude) ** 2
            for anchor_latitude, anchor_longitude in anchors
        ) / len(anchors)

    chosen = min(
        with_coordinates,
        key=lambda item: (
            route_cost(item),
            -float(item.get("score") or 0),
            str(item.get("entityId") or ""),
        ),
    )
    return {**chosen, "routeScore": round(route_cost(chosen), 8)}


def _artifact_hash(artifacts: dict) -> str:
    payload = json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _numeric_user_id(user_id: str | None) -> int | None:
    return int(user_id) if user_id is not None and user_id.isdigit() else None


def _priority_from_confidence(confidence: float) -> int:
    if confidence >= 0.85:
        return 1
    if confidence >= 0.7:
        return 2
    if confidence >= 0.5:
        return 3
    return 4


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalized(value)).strip("-") or "unknown"
