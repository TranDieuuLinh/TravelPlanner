"""Reconcile curated nighttime Activities and their evidence-backed offerings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.tag_model import KnowledgeEntityTagAssertion
from app.modules.knowledge_graph.text import normalize_knowledge_text


HANOI_ID = "area_city_0c21619b4e"
CATALOG_SOURCE = "curation:hanoi-evening-fallback:v1"
OFFER_SOURCE = "classifier:night-activity-offers:v1"
LEGACY_INFERENCE_SOURCE = "inference:activity-taxonomy:v1"


@dataclass(frozen=True)
class NightActivityDefinition:
    activity_id: str
    name: str
    category: str
    activity_tags: tuple[str, ...]
    windows: tuple[tuple[str, str], ...]
    duration: int
    minimum_gap: int


NIGHT_ACTIVITIES = (
    NightActivityDefinition("activity_evening_cultural_performance", "Xem biểu diễn văn hóa buổi tối", "culture", ("performance", "indoor", "ticketed", "family_friendly"), (("18:30", "21:30"),), 90, 75),
    NightActivityDefinition("activity_live_music", "Nghe nhạc sống buổi tối", "entertainment", ("live_music", "acoustic", "jazz", "reservation_recommended"), (("19:00", "23:00"),), 120, 90),
    NightActivityDefinition("activity_evening_city_walk", "Đi bộ khám phá thành phố buổi tối", "outdoor", ("walking", "night_view", "free", "weather_sensitive"), (("19:00", "21:30"),), 90, 60),
    NightActivityDefinition("activity_night_market", "Khám phá chợ đêm", "local_life", ("market", "street_food", "shopping", "crowded"), (("19:00", "22:30"),), 120, 90),
    NightActivityDefinition("activity_rooftop_city_view", "Ngắm thành phố từ rooftop buổi tối", "city_view", ("rooftop", "night_view", "weather_sensitive", "adult_optional"), (("19:00", "23:00"),), 90, 60),
    NightActivityDefinition("activity_night_sightseeing_tour", "Tham quan Hà Nội về đêm", "sightseeing", ("guided_tour", "ticketed", "fixed_schedule"), (("18:30", "22:00"),), 120, 90),
    NightActivityDefinition("activity_nightlife_drink", "Trải nghiệm đồ uống buổi tối", "nightlife", ("bar", "cocktail", "alcohol", "adult_only"), (("19:00", "23:30"),), 90, 60),
    NightActivityDefinition("activity_karaoke", "Hát karaoke", "entertainment", ("karaoke", "group_friendly", "indoor", "reservation_recommended"), (("19:00", "23:30"),), 120, 90),
    NightActivityDefinition("activity_wellness_evening", "Thư giãn và chăm sóc sức khỏe buổi tối", "wellness", ("spa", "massage", "indoor", "reservation_recommended"), (("18:30", "22:00"),), 90, 60),
)

MANUAL_OFFERS: dict[str, tuple[str, ...]] = {
    "activity_evening_cultural_performance": (
        "travel_place_ChIJiUJFE8CrNTERHK060qWnXk4",
    ),
    "activity_live_music": (
        "travel_place_ChIJd7J8AOyrNTERL8q8mpttgeA",
        "travel_place_ChIJ5d40VmirNTER1B49ry4TXRQ",
        "travel_place_ChIJm6F3sZGrNTERguWWeYzilbo",
        "drink_dessert_ChIJR2xGCwCrNTERQ4_nk9hQrBQ",
    ),
    "activity_evening_city_walk": (
        "travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k",
        "travel_place_ChIJCVruNJWrNTERIAbKBaOYZ2w",
    ),
    "activity_night_market": (
        "travel_place_ChIJC1uSGbmrNTERvIuiy_FZMzA",
        "travel_place_ChIJ3x01HQCrNTERtBCN9T55LnI",
    ),
    "activity_rooftop_city_view": (
        # Exact-name Hà Nội rooftop/sky-bar records, reviewed against stored
        # provider category, address, rating and review-count properties.
        "drink_dessert_ChIJsw-cTRurNTERI7xBLEdeJnI",  # AIRA Sky Bar & Lounge
        "drink_dessert_ChIJAQA8NsCrNTERejuYHqk4EG8",  # Diamond Sky Bar
        "drink_dessert_ChIJ7SLeZQirNTERS4Ibezb56Ho",  # Lighthouse Sky Bar
    ),
    "activity_night_sightseeing_tour": (
        "travel_place_ChIJVUvVbACrNTERzY_ZFRXbAKc",
    ),
    "activity_nightlife_drink": (
        "travel_place_ChIJd64Vx8CrNTERulxZIacQ3Bg",
    ),
}

TAG_ACTIVITY_RULES: dict[str, tuple[tuple[str, ...], ...]] = {
    "activity_live_music": (("live_music",), ("jazz",)),
    "activity_rooftop_city_view": (("rooftop",),),
    "activity_night_sightseeing_tour": (("guided_tour", "late_night"),),
    "activity_nightlife_drink": (("alcohol",),),
    "activity_karaoke": (("karaoke",),),
    "activity_wellness_evening": (("spa", "late_night"), ("massage", "late_night")),
}

BROAD_SPECIAL_ACTIVITY_IDS = (
    "activity_coffee",
    "activity_cultural_visit",
    "activity_shopping",
    "activity_walk_outdoors",
    "activity_nightlife_drink",
    "activity_eat_pho",
)


class NightActivityCatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.changes: list[str] = []

    def reconcile(self) -> dict[str, Any]:
        self._require_manual_places()
        for definition in NIGHT_ACTIVITIES:
            self._upsert_activity(definition)
        self._remove_broad_special_edges()
        self._remove_legacy_inferred_night_offers()
        # A legacy edge may also qualify under the new evidence rules. Flush
        # deletions before upsert lookup so it is recreated with the new source
        # in this same reconciliation run rather than disappearing until rerun.
        self.db.flush()
        candidates = self._effective_tag_sets()
        desired_offers: dict[str, set[str]] = {}
        for definition in NIGHT_ACTIVITIES:
            place_ids = set(MANUAL_OFFERS.get(definition.activity_id, ()))
            for place_id, tags in candidates.items():
                rules = TAG_ACTIVITY_RULES.get(definition.activity_id, ())
                if any(set(rule).issubset(tags) for rule in rules):
                    place_ids.add(place_id)
            desired_offers[definition.activity_id] = place_ids
        self._remove_stale_classifier_offers(desired_offers)
        self.db.flush()
        for definition in NIGHT_ACTIVITIES:
            place_ids = desired_offers[definition.activity_id]
            for place_id in sorted(place_ids):
                self._upsert_edge(place_id, "OFFERS_ACTIVITY", definition.activity_id)
        self.db.flush()
        return {
            "changeCount": len(self.changes),
            "changes": self.changes,
            "nightActivityCount": len(NIGHT_ACTIVITIES),
            "specialExperienceEdgesCreated": 0,
        }

    def _require_manual_places(self) -> None:
        required = {place_id for values in MANUAL_OFFERS.values() for place_id in values}
        found = set(
            self.db.scalars(select(KnowledgeEntity.id).where(KnowledgeEntity.id.in_(required)))
        )
        missing = sorted(required - found)
        if missing:
            raise RuntimeError(f"Curated nighttime places are missing: {', '.join(missing)}")

    def _upsert_activity(self, definition: NightActivityDefinition) -> None:
        entity = self.db.get(KnowledgeEntity, definition.activity_id)
        if entity is None:
            entity = KnowledgeEntity(
                id=definition.activity_id,
                canonical_name=definition.name,
                normalized_name=normalize_knowledge_text(definition.name),
                entity_type="Activity",
                status="verified",
            )
            self.db.add(entity)
            self.changes.append(f"create entity {definition.activity_id}")
        else:
            values = {
                "canonical_name": definition.name,
                "normalized_name": normalize_knowledge_text(definition.name),
                "entity_type": "Activity",
                "status": "verified",
            }
            if any(getattr(entity, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(entity, key, value)
                self.changes.append(f"update entity {definition.activity_id}")
        properties = {
            "description": f"Hoạt động tùy chọn dùng để lấp khoảng trống buổi tối: {definition.name}.",
            "activity_category": definition.category,
            "activity_tags": list(definition.activity_tags),
            "fallback_role": "evening_gap_fill",
            "eligible_day_parts": ["evening"],
            "preferred_time_windows": [
                {"start": start, "end": end} for start, end in definition.windows
            ],
            "typical_duration_minutes": definition.duration,
            "minimum_gap_minutes": definition.minimum_gap,
            "maximum_items_per_day": 1,
        }
        for key, value in properties.items():
            self._upsert_property(definition.activity_id, key, value)

    def _upsert_property(self, entity_id: str, key: str, value: Any) -> None:
        stored = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (list, dict)) else str(value)
        row = self.db.scalar(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
                KnowledgeProperty.key == key,
            )
        )
        if row is None:
            self.db.add(KnowledgeProperty(entity_id=entity_id, key=key, value=stored, source=CATALOG_SOURCE))
            self.changes.append(f"create property {entity_id}:{key}")
        elif row.value != stored or row.source != CATALOG_SOURCE:
            row.value = stored
            row.source = CATALOG_SOURCE
            self.changes.append(f"update property {entity_id}:{key}")

    def _remove_broad_special_edges(self) -> None:
        rows = list(
            self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.from_entity_id == HANOI_ID,
                    KnowledgeRelationship.relationship_type == "SPECIAL_EXPERIENCE",
                    KnowledgeRelationship.to_entity_id.in_(BROAD_SPECIAL_ACTIVITY_IDS),
                )
            )
        )
        for row in rows:
            self.db.delete(row)
            self.changes.append(f"delete broad special edge {row.to_entity_id}")

    def _remove_legacy_inferred_night_offers(self) -> None:
        activity_ids = [definition.activity_id for definition in NIGHT_ACTIVITIES]
        rows = list(
            self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.relationship_type == "OFFERS_ACTIVITY",
                    KnowledgeRelationship.to_entity_id.in_(activity_ids),
                    KnowledgeRelationship.source == LEGACY_INFERENCE_SOURCE,
                )
            )
        )
        for row in rows:
            self.db.delete(row)
            self.changes.append(f"delete legacy offer {row.from_entity_id}:{row.to_entity_id}")

    def _remove_stale_classifier_offers(
        self,
        desired_offers: dict[str, set[str]],
    ) -> None:
        activity_ids = list(desired_offers)
        rows = list(
            self.db.scalars(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.relationship_type == "OFFERS_ACTIVITY",
                    KnowledgeRelationship.to_entity_id.in_(activity_ids),
                    KnowledgeRelationship.source == OFFER_SOURCE,
                )
            )
        )
        for row in rows:
            if row.from_entity_id in desired_offers[row.to_entity_id]:
                continue
            self.db.delete(row)
            self.changes.append(
                f"delete stale classified offer {row.from_entity_id}:{row.to_entity_id}"
            )

    def _effective_tag_sets(self) -> dict[str, set[str]]:
        rows = self.db.execute(
            select(
                KnowledgeEntityTagAssertion.entity_id,
                KnowledgeEntityTagAssertion.tag_key,
            ).where(
                KnowledgeEntityTagAssertion.status.in_(("verified", "source_backed")),
                KnowledgeEntityTagAssertion.confidence >= 0.90,
                or_(
                    KnowledgeEntityTagAssertion.expires_at.is_(None),
                    KnowledgeEntityTagAssertion.expires_at > func.now(),
                ),
            )
        )
        tags: dict[str, set[str]] = {}
        for entity_id, tag_key in rows:
            tags.setdefault(entity_id, set()).add(tag_key)
        return tags

    def _upsert_edge(self, from_id: str, relationship_type: str, to_id: str) -> None:
        row = self.db.scalar(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.from_entity_id == from_id,
                KnowledgeRelationship.relationship_type == relationship_type,
                KnowledgeRelationship.to_entity_id == to_id,
            )
        )
        if row is None:
            self.db.add(
                KnowledgeRelationship(
                    from_entity_id=from_id,
                    relationship_type=relationship_type,
                    to_entity_id=to_id,
                    recommendations=[],
                    source=OFFER_SOURCE,
                )
            )
            self.changes.append(f"create offer {from_id}:{to_id}")
        elif row.source == LEGACY_INFERENCE_SOURCE:
            row.source = OFFER_SOURCE
            self.changes.append(f"update offer {from_id}:{to_id}")
