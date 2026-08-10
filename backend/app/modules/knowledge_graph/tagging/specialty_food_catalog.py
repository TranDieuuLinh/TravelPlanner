"""Reconcile Hanoi food/drink specialties as item-backed Activities.

The catalog deliberately does not create ``OFFERS_ACTIVITY`` edges. A venue
serves an Item; the destination-specific Activity involves that Item.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.tagging.catalog import HANOI_ID
from app.modules.knowledge_graph.text import normalize_knowledge_text


CATALOG_SOURCE = "curation:hanoi-specialty-food-items:v1"
VENUE_TYPES = frozenset({"Restaurant", "DrinkDessert"})


@dataclass(frozen=True)
class SpecialtyDefinition:
    key: str
    name: str
    item_type: str
    item_category: str
    activity_category: str
    patterns: tuple[str, ...]
    venue_types: frozenset[str]
    windows: tuple[tuple[str, str], ...]
    duration_minutes: int

    @property
    def item_id(self) -> str:
        prefix = "food_item" if self.item_type == "FoodItem" else "drink_item"
        return f"{prefix}_hanoi_{self.key}"

    @property
    def activity_id(self) -> str:
        return f"activity_hanoi_{self.key}"


MEAL_WINDOWS = (("07:00", "10:00"), ("11:00", "14:00"), ("18:00", "21:00"))
SNACK_WINDOWS = (("09:00", "11:00"), ("14:00", "18:00"), ("19:00", "21:30"))
DRINK_WINDOWS = (("07:00", "11:00"), ("14:00", "21:00"))
RESTAURANT = frozenset({"Restaurant"})
FOOD_VENUE = VENUE_TYPES
DRINK_VENUE = frozenset({"DrinkDessert", "Restaurant"})


def _meal(key: str, name: str, *patterns: str) -> SpecialtyDefinition:
    return SpecialtyDefinition(
        key, name, "FoodItem", "main_dish", "dining", patterns,
        RESTAURANT, MEAL_WINDOWS, 60,
    )


def _snack(key: str, name: str, *patterns: str) -> SpecialtyDefinition:
    return SpecialtyDefinition(
        key, name, "FoodItem", "snack", "dessert", patterns,
        FOOD_VENUE, SNACK_WINDOWS, 45,
    )


def _drink(key: str, name: str, *patterns: str) -> SpecialtyDefinition:
    return SpecialtyDefinition(
        key, name, "DrinkItem", "beverage", "beverage", patterns,
        DRINK_VENUE, DRINK_WINDOWS, 45,
    )


SPECIALTIES = (
    _meal("pho_bo", "Phở bò", r"\bpho bo\b"),
    _meal("pho_ga", "Phở gà", r"\bpho ga\b"),
    _meal("bun_cha", "Bún chả", r"\bbun cha\b"),
    _meal("bun_thang", "Bún thang", r"\bbun thang\b"),
    _meal("bun_dau_mam_tom", "Bún đậu mắm tôm", r"\bbun dau mam tom\b"),
    _meal("cha_ca_la_vong", "Chả cá Lã Vọng", r"\bcha ca\b"),
    _meal("banh_mi", "Bánh mì Hà Nội", r"\bbanh (?:mi|my)\b"),
    _meal("banh_cuon", "Bánh cuốn Hà Nội", r"\bbanh cuon\b"),
    _meal("bun_oc", "Bún ốc", r"\bbun oc\b"),
    _meal("bun_rieu_cua", "Bún riêu cua", r"\bbun (?:oc )?rieu\b", r"\brieu cua\b"),
    _meal("xoi_xeo", "Xôi xéo", r"\bxoi xeo\b"),
    _meal("pho_cuon", "Phở cuốn", r"\bpho cuon\b"),
    _meal("bun_moc", "Bún mọc", r"\bbun moc\b"),
    _meal("bun_doc_mung", "Bún dọc mùng", r"\bbun doc mung\b"),
    _meal("banh_gio", "Bánh giò", r"\bbanh gio\b"),
    _meal("bun_ca", "Bún cá", r"\bbun ca\b"),
    _meal("chao_suon", "Cháo sườn", r"\bchao suon\b"),
    _meal("chao_trai", "Cháo trai", r"\bchao trai\b"),
    _meal("banh_bao", "Bánh bao", r"\bbanh bao\b"),
    _meal("banh_mi_chao", "Bánh mì chảo", r"\bbanh (?:mi|my) chao\b"),
    _meal("bun_ngan", "Bún ngan", r"\bbun ngan\b"),
    _meal("banh_xeo", "Bánh xèo", r"\bbanh xeo\b"),
    _snack("banh_tom_ho_tay", "Bánh tôm Hồ Tây", r"\bbanh tom\b"),
    _snack("nem_ran", "Nem rán", r"\bnem ran\b"),
    _snack("nom_bo_kho", "Nộm bò khô", r"\bnom bo kho\b"),
    _snack("banh_ran_man", "Bánh rán mặn", r"\bbanh ran man\b"),
    _snack("banh_ran_ngot", "Bánh rán ngọt", r"\bbanh ran[^|]*ngot\b"),
    _snack("kem_trang_tien", "Kem Tràng Tiền", r"\bkem trang tien\b", r"\btrang tien ice cream\b"),
    _snack("banh_com", "Bánh cốm", r"\bbanh com\b"),
    _snack("cha_ruoi", "Chả rươi", r"\bcha ruoi\b"),
    _snack("bun_cha_chan", "Bún chả chan", r"\bbun cha chan\b"),
    _snack("banh_duc_nong", "Bánh đúc nóng", r"\bbanh duc nong\b"),
    _snack("banh_goi", "Bánh gối", r"\bbanh goi\b"),
    _snack("nem_chua_ran", "Nem chua rán", r"\bnem chua ran\b"),
    _snack("banh_trang_tron", "Bánh tráng trộn", r"\bbanh trang tron\b"),
    _snack("tao_pho", "Tào phớ", r"\btao pho\b"),
    _snack("che_thap_cam", "Chè thập cẩm", r"\bche thap cam\b"),
    # Vietnamese "cà phê trứng" cannot be matched safely by token prefix:
    # "Cà phê Trung Nguyên" would be a false positive. Vietnamese venues come
    # from the legacy evidence-backed TARGETS_PLACE mappings; English names may
    # still match the unambiguous phrase below.
    _drink("ca_phe_trung", "Cà phê trứng", r"\begg coffee\b"),
    _drink("tra_da", "Trà đá vỉa hè", r"\btra da\b"),
    _drink("bia_hoi", "Bia hơi", r"\bbia hoi\b"),
)


# Old place-specific Activities are deleted after their TARGETS_PLACE venues
# have provided evidence for the replacement item type.
LEGACY_ACTIVITY_TO_KEY: dict[str, str | None] = {
    "activity_special_42a56958cb805b12": "pho_bo",
    "activity_special_08187177a10ea41d": "pho_bo",
    "activity_special_e2f420ed516ae5b3": "bun_cha",
    "activity_special_f9127ce42a0350cc": "bun_cha",
    "activity_special_74f7c6dcfee57c59": "ca_phe_trung",
    "activity_special_d2f959c282e475c0": "ca_phe_trung",
    "activity_special_68ff0e771fa2349a": "banh_mi",
    "activity_special_a066f0ba71fb4f1c": "pho_cuon",
    "activity_special_1bde20c515f0e46b": "banh_cuon",
    "activity_special_b19d1a25880ef528": "bia_hoi",
    "activity_special_cc4824968a6b76ab": "kem_trang_tien",
    # These place-specific experiences have no supported replacement in the
    # approved list and are deleted without creating a replacement.
    "activity_special_4563298ff11497e7": None,
    "activity_special_8cf29f81fdccbade": None,
}


UNSUPPORTED_OR_MERGED = (
    "Bánh mì sốt vang",
    "Chè sen long nhãn",
    "Cà phê sữa đá",
    "Ô mai",
    "Sữa chua nếp cẩm",
    "Nước sấu",
    "Nước mơ",
    "Bánh chưng",
    "Bánh dày",
    "Chè (quá rộng; chỉ giữ Chè thập cẩm)",
    "Bún đậu (gộp vào Bún đậu mắm tôm)",
    "Bánh cuốn Thanh Trì (gộp vào Bánh cuốn Hà Nội)",
    "Bánh tôm (gộp vào Bánh tôm Hồ Tây)",
    "Bánh mì (gộp vào Bánh mì Hà Nội)",
    "Trà đá (gộp vào Trà đá vỉa hè)",
)


class HanoiSpecialtyFoodCatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.changes: list[str] = []

    def reconcile(self) -> dict[str, Any]:
        area = self.db.get(KnowledgeEntity, HANOI_ID)
        if area is None:
            raise RuntimeError(f"Hanoi Area is missing: {HANOI_ID}")

        venues = list(
            self.db.scalars(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.entity_type.in_(VENUE_TYPES)
                )
            )
        )
        legacy_venues = self._legacy_target_venues()
        self._delete_legacy_activities()

        supported: list[dict[str, Any]] = []
        for definition in SPECIALTIES:
            matched = {
                venue.id
                for venue in venues
                if venue.entity_type in definition.venue_types
                and any(
                    re.search(pattern, venue.normalized_name)
                    for pattern in definition.patterns
                )
            }
            matched.update(
                venue_id
                for venue_id in legacy_venues.get(definition.key, set())
                if (venue := self.db.get(KnowledgeEntity, venue_id)) is not None
                and venue.entity_type in definition.venue_types
            )
            if not matched:
                continue
            self._upsert_definition(area.id, definition, matched)
            supported.append(
                {
                    "name": definition.name,
                    "itemType": definition.item_type,
                    "venueCount": len(matched),
                }
            )

        self.db.flush()
        return {
            "supportedCount": len(supported),
            "supported": supported,
            "unsupportedOrMerged": list(UNSUPPORTED_OR_MERGED),
            "changeCount": len(self.changes),
            "changes": self.changes,
        }

    def _legacy_target_venues(self) -> dict[str, set[str]]:
        rows = self.db.execute(
            select(
                KnowledgeRelationship.from_entity_id,
                KnowledgeRelationship.to_entity_id,
            ).where(
                KnowledgeRelationship.relationship_type == "TARGETS_PLACE",
                KnowledgeRelationship.from_entity_id.in_(LEGACY_ACTIVITY_TO_KEY),
            )
        ).all()
        result: dict[str, set[str]] = {}
        for activity_id, venue_id in rows:
            key = LEGACY_ACTIVITY_TO_KEY.get(activity_id)
            if key is not None:
                result.setdefault(key, set()).add(venue_id)
        return result

    def _delete_legacy_activities(self) -> None:
        activities = list(
            self.db.scalars(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.id.in_(LEGACY_ACTIVITY_TO_KEY),
                    KnowledgeEntity.entity_type == "Activity",
                )
            )
        )
        for activity in activities:
            self.db.delete(activity)
            self.changes.append(f"delete legacy Activity {activity.id}")

    def _upsert_definition(
        self,
        area_id: str,
        definition: SpecialtyDefinition,
        venue_ids: set[str],
    ) -> None:
        item = self._upsert_entity(
            definition.item_id,
            definition.name,
            definition.item_type,
        )
        activity = self._upsert_entity(
            definition.activity_id,
            f"Thưởng thức {definition.name.casefold()}",
            "Activity",
        )
        self._upsert_property(
            item.id,
            "description",
            f"Món đặc trưng Hà Nội: {definition.name}.",
        )
        self._upsert_property(item.id, "item_category", definition.item_category)
        self._upsert_property(
            activity.id,
            "description",
            f"Trải nghiệm thưởng thức {definition.name} tại một venue phù hợp ở Hà Nội.",
        )
        self._upsert_property(
            activity.id,
            "activity_category",
            definition.activity_category,
        )
        self._upsert_property(
            activity.id,
            "typical_duration_minutes",
            str(definition.duration_minutes),
        )
        self._upsert_property(
            activity.id,
            "best_time_slots",
            json.dumps(
                [
                    {"start": start, "end": end}
                    for start, end in definition.windows
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        self._upsert_edge(
            area_id,
            "SPECIAL_EXPERIENCE",
            activity.id,
            recommendations=[
                {
                    "priority": "recommended",
                    "intent": (
                        "drink" if definition.item_type == "DrinkItem" else "eat"
                    ),
                    "recommendedItems": [definition.name],
                    "recommendedVisitMinutes": definition.duration_minutes,
                    "timeSlots": [
                        {"start": start, "end": end}
                        for start, end in definition.windows
                    ],
                    "reason": (
                        f"{definition.name} được giữ trong catalog đặc trưng vì "
                        "Knowledge Graph có venue phù hợp từ tên venue hoặc "
                        "TARGETS_PLACE có provenance."
                    ),
                }
            ],
        )
        self._upsert_edge(activity.id, "INVOLVES_ITEM", item.id)
        for venue_id in sorted(venue_ids):
            self._upsert_edge(venue_id, "OFFERS_ITEM", item.id)

    def _upsert_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
    ) -> KnowledgeEntity:
        entity = self.db.get(KnowledgeEntity, entity_id)
        values = {
            "canonical_name": name,
            "normalized_name": normalize_knowledge_text(name),
            "entity_type": entity_type,
            "status": "verified",
        }
        if entity is None:
            entity = KnowledgeEntity(id=entity_id, **values)
            self.db.add(entity)
            self.changes.append(f"create entity {entity_id}")
        elif any(getattr(entity, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(entity, key, value)
            self.changes.append(f"update entity {entity_id}")
        return entity

    def _upsert_property(self, entity_id: str, key: str, value: str) -> None:
        row = self.db.scalar(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id == entity_id,
                KnowledgeProperty.key == key,
            )
        )
        if row is None:
            self.db.add(
                KnowledgeProperty(
                    entity_id=entity_id,
                    key=key,
                    value=value,
                    source=CATALOG_SOURCE,
                )
            )
            self.changes.append(f"create property {entity_id}:{key}")
        elif row.value != value or row.source != CATALOG_SOURCE:
            row.value = value
            row.source = CATALOG_SOURCE
            self.changes.append(f"update property {entity_id}:{key}")

    def _upsert_edge(
        self,
        from_id: str,
        relationship_type: str,
        to_id: str,
        *,
        recommendations: list[dict[str, Any]] | None = None,
    ) -> None:
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
                    recommendations=recommendations,
                    source=CATALOG_SOURCE,
                )
            )
            self.changes.append(
                f"create edge {from_id}:{relationship_type}:{to_id}"
            )
        elif row.source != CATALOG_SOURCE or (
            recommendations is not None and row.recommendations != recommendations
        ):
            row.source = CATALOG_SOURCE
            if recommendations is not None:
                row.recommendations = recommendations
            self.changes.append(
                f"update edge {from_id}:{relationship_type}:{to_id}"
            )
