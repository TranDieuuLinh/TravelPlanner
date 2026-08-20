from dataclasses import dataclass

from app.modules.place_checker.analysis.contract import (
    CapacityAnalysis,
    DurationLoadAnalysis,
    GeographicOverheadAnalysis,
)
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    CapacityLoadStatus,
    GeographicSpread,
    ItemResolutionStatus,
    PlaceLifecycleState,
    SourceTier,
)
from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.resolution.item_contract import ItemResolutionBatch
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.scoring import distance_km


@dataclass(frozen=True)
class _DurationRecord:
    place_id: str
    group: str
    minimum: int | None
    typical: int | None
    maximum: int | None
    coordinates: Coordinates | None


class CapacityAnalysisService:
    def analyze(
        self,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        context: TripEvaluationContext,
    ) -> CapacityAnalysis:
        records = self._records(places, items)
        mandatory = self._load(records, "mandatory")
        preferred = self._load(records, "preferred")
        optional = self._load(records, "optional")
        total = self._load(records)
        overhead = self._overhead(records)
        mandatory_overhead = self._overhead(
            [record for record in records if record.group == "mandatory"]
        )
        status, utilization = self._status(
            total,
            mandatory,
            overhead,
            mandatory_overhead.estimated_minutes,
            context,
        )
        warnings: list[str] = []
        if (
            mandatory.minimum_minutes + mandatory_overhead.estimated_minutes
            > context.capacity.maximum_minutes
        ):
            warnings.append("Mandatory load vượt capacity tối đa; không tự loại place.")
        if total.unknown_duration_count:
            warnings.append(
                f"{total.unknown_duration_count} place(s) chưa có typical duration."
            )
        return CapacityAnalysis(
            status=status,
            available_minutes=context.capacity,
            mandatory=mandatory,
            preferred=preferred,
            optional=optional,
            total=total,
            geographic_overhead=overhead,
            typical_utilization=utilization,
            warnings=warnings,
        )

    @staticmethod
    def _records(
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
    ) -> list[_DurationRecord]:
        records: list[_DurationRecord] = []
        seen_ids: set[str] = set()
        for index, evaluation in enumerate(places.places):
            place = evaluation.place
            if not place.mandatory and evaluation.state == PlaceLifecycleState.rejected:
                continue
            identity = place.place_id or f"unresolved:{index}"
            seen_ids.add(identity)
            metadata = place.metadata
            group = (
                "mandatory"
                if place.mandatory
                else (
                    "preferred"
                    if place.source_tier in {SourceTier.url, SourceTier.item_resolved}
                    else "optional"
                )
            )
            records.append(
                _DurationRecord(
                    identity,
                    group,
                    metadata.minimum_duration_minutes if metadata else None,
                    metadata.typical_duration_minutes if metadata else None,
                    metadata.maximum_duration_minutes if metadata else None,
                    metadata.coordinates if metadata else None,
                )
            )
        for item in items.items:
            if (
                item.status != ItemResolutionStatus.resolved
                or item.selected is None
                or item.selected.place_id in seen_ids
            ):
                continue
            selected = item.selected
            seen_ids.add(selected.place_id)
            records.append(
                _DurationRecord(
                    selected.place_id,
                    "preferred",
                    selected.minimum_duration_minutes,
                    selected.typical_duration_minutes,
                    selected.maximum_duration_minutes,
                    selected.coordinates,
                )
            )
        return records

    @staticmethod
    def _load(
        records: list[_DurationRecord],
        group: str | None = None,
    ) -> DurationLoadAnalysis:
        selected = [record for record in records if group is None or record.group == group]
        return DurationLoadAnalysis(
            place_count=len(selected),
            known_duration_count=sum(record.typical is not None for record in selected),
            unknown_duration_count=sum(record.typical is None for record in selected),
            minimum_minutes=sum(record.minimum or 0 for record in selected),
            typical_minutes=sum(record.typical or 0 for record in selected),
            maximum_minutes=sum(record.maximum or 0 for record in selected),
        )

    @staticmethod
    def _overhead(records: list[_DurationRecord]) -> GeographicOverheadAnalysis:
        coordinates = [record.coordinates for record in records if record.coordinates]
        unknown = len(records) - len(coordinates)
        if len(coordinates) < 2:
            return GeographicOverheadAnalysis(
                known_coordinate_count=len(coordinates),
                unknown_coordinate_count=unknown,
                spread=GeographicSpread.unknown,
            )
        center = Coordinates(
            latitude=sum(point.latitude for point in coordinates) / len(coordinates),
            longitude=sum(point.longitude for point in coordinates) / len(coordinates),
        )
        radius = max(distance_km(center, point) for point in coordinates)
        if radius <= 2:
            spread, per_transition = GeographicSpread.compact, 15
        elif radius <= 8:
            spread, per_transition = GeographicSpread.moderate, 30
        else:
            spread, per_transition = GeographicSpread.dispersed, 45
        return GeographicOverheadAnalysis(
            known_coordinate_count=len(coordinates),
            unknown_coordinate_count=unknown,
            spread=spread,
            radius_km=round(radius, 3),
            estimated_minutes=(len(coordinates) - 1) * per_transition,
        )

    @staticmethod
    def _status(
        total: DurationLoadAnalysis,
        mandatory: DurationLoadAnalysis,
        overhead: GeographicOverheadAnalysis,
        mandatory_overhead_minutes: int,
        context: TripEvaluationContext,
    ) -> tuple[CapacityLoadStatus, float | None]:
        typical_load = total.typical_minutes + overhead.estimated_minutes
        utilization = (
            round(typical_load / context.capacity.typical_minutes, 6)
            if context.capacity.typical_minutes
            else None
        )
        minimum_load = total.minimum_minutes + overhead.estimated_minutes
        mandatory_minimum = mandatory.minimum_minutes + mandatory_overhead_minutes
        if (
            minimum_load > context.capacity.maximum_minutes
            or mandatory_minimum > context.capacity.maximum_minutes
            or typical_load > context.capacity.maximum_minutes
        ):
            return CapacityLoadStatus.overloaded, utilization
        if total.place_count and total.known_duration_count == 0:
            return CapacityLoadStatus.unknown, utilization
        if total.unknown_duration_count:
            return CapacityLoadStatus.at_risk, utilization
        if utilization is None or utilization < 0.60:
            return CapacityLoadStatus.underloaded, utilization
        if utilization <= 1.0:
            return CapacityLoadStatus.balanced, utilization
        return CapacityLoadStatus.at_risk, utilization
