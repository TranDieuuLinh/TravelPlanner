"""Map Knowledge Graph relationship rows into PlaceChecker evidence."""

import json


class PostgresRelationshipMappingMixin:
    @staticmethod
    def _metadata_relationship(row, *, target_properties=None, style_properties=None):
        target_properties = target_properties or style_properties
        raw = row["recommendations"]
        try:
            recommendations = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            recommendations = {}
        payload = recommendations if isinstance(recommendations, dict) else {}
        evidence = recommendations if isinstance(recommendations, list) else []
        confidences = [
            item.get("confidence")
            for item in evidence
            if isinstance(item, dict)
            and isinstance(item.get("confidence"), (int, float))
        ]
        kind = row["relationship_type"]
        distance = payload.get("distance_km")
        threshold = payload.get("threshold_km")
        if kind == "Special_Near":
            ratio = distance / threshold if distance is not None and threshold else 1
            score = max(0.65, 0.95 - 0.30 * ratio)
        elif kind == "Special_Experience":
            score = 0.55 if payload.get("status") == "pending" else 0.78
        elif kind == "Offer_Item":
            score = max(
                confidences,
                default=0.45 if payload.get("status") == "pending" else 0.72,
            )
        else:
            score = min(0.75, 0.45 + float(payload.get("priority", 40)) / 400)
        properties = dict(target_properties or {})
        if kind == "Offer_Item":
            properties["entityType"] = row.get("related_entity_type")
        properties.update(payload.get("properties") or {})
        return {
            "relationshipType": kind,
            "direction": row["direction"],
            "scope": row["scope"],
            "fromEntityId": row["from_entity_id"],
            "toEntityId": row["to_entity_id"],
            "relatedEntityId": row["related_entity_id"],
            "relatedName": row["related_name"],
            "status": payload.get("status"),
            "confidence": max(confidences) if confidences else None,
            "priority": payload.get("priority"),
            "distanceKm": distance,
            "thresholdKm": threshold,
            "source": row["source"],
            "sourceNote": row["source_note"],
            "properties": properties,
            "score": min(1, max(0, score)),
        }
