from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.modules.places.auto_statistics.domain import (
    ALGORITHM_VERSION,
    build_region_statistics,
    utc_now,
)
from app.modules.places.repository import PlaceStatisticsRepository


@dataclass(frozen=True)
class AutoStatisticsRefreshResult:
    status: str
    output_path: Path
    source_row_count: int
    region_count: int
    source_fingerprint: str


@dataclass(frozen=True)
class PlannerRegionStatisticsResult:
    status: str
    region_key: str
    regions: list[dict[str, Any]]
    snapshot_id: str
    catalog_version: int
    algorithm_version: str
    generated_at: str
    source_fingerprint: str


class AutoPlaceStatisticsService:
    def __init__(
        self,
        repository: PlaceStatisticsRepository,
        output_path: Path,
        *,
        stale_after_days: int = 30,
        snapshot_ttl_hours: int = 24,
    ) -> None:
        if stale_after_days < 1:
            raise ValueError("stale_after_days must be at least 1")
        if snapshot_ttl_hours < 1:
            raise ValueError("snapshot_ttl_hours must be at least 1")
        self.repository = repository
        self.output_path = output_path.resolve()
        self.stale_after_days = stale_after_days
        self.snapshot_ttl_hours = snapshot_ttl_hours

    def refresh(self, *, force: bool = False) -> AutoStatisticsRefreshResult:
        source_signature = self.repository.source_signature()
        existing = self._read_existing(self.output_path)
        if not force and self._is_current(existing, source_signature):
            return AutoStatisticsRefreshResult(
                status="unchanged",
                output_path=self.output_path,
                source_row_count=int(existing["source"]["rowCount"]),
                region_count=len(existing["regions"]),
                source_fingerprint=str(source_signature["fingerprint"]),
            )

        generated_at = utc_now()
        stale_before = generated_at - timedelta(days=self.stale_after_days)
        regions, row_count = build_region_statistics(
            self.repository.iter_statistics_records(),
            stale_before=stale_before,
        )

        signature_after_read = self.repository.source_signature()
        if signature_after_read["fingerprint"] != source_signature["fingerprint"]:
            raise RuntimeError(
                "Place catalog changed while statistics were being calculated"
            )

        output = {
            "schemaVersion": "1.0",
            "algorithmVersion": ALGORITHM_VERSION,
            "generatedAt": generated_at.isoformat(),
            "staleAfterDays": self.stale_after_days,
            "rollupPolicy": "Each Place contributes to every region_key prefix from city level.",
            "source": {
                **source_signature,
                "rowCount": row_count,
            },
            "regions": regions,
        }
        self._atomic_write(output, self.output_path)
        return AutoStatisticsRefreshResult(
            status="refreshed",
            output_path=self.output_path,
            source_row_count=row_count,
            region_count=len(regions),
            source_fingerprint=str(source_signature["fingerprint"]),
        )

    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> PlannerRegionStatisticsResult:
        source_signature = self.repository.source_signature(region_key)
        current_snapshot = self.repository.get_current_snapshot(region_key)
        if (
            not force
            and current_snapshot is not None
            and current_snapshot.algorithm_version == ALGORITHM_VERSION
            and current_snapshot.source_fingerprint
            == source_signature["fingerprint"]
            and _is_future(current_snapshot.expires_at, utc_now())
        ):
            return PlannerRegionStatisticsResult(
                status="cached",
                region_key=region_key,
                regions=current_snapshot.metrics_json["regions"],
                snapshot_id=current_snapshot.id,
                catalog_version=current_snapshot.catalog_version,
                algorithm_version=current_snapshot.algorithm_version,
                generated_at=current_snapshot.generated_at.isoformat(),
                source_fingerprint=str(source_signature["fingerprint"]),
            )

        generated_at = utc_now()
        stale_before = generated_at - timedelta(days=self.stale_after_days)
        regions, row_count = build_region_statistics(
            self.repository.iter_statistics_records(region_key),
            stale_before=stale_before,
        )
        signature_after_read = self.repository.source_signature(region_key)
        if signature_after_read["fingerprint"] != source_signature["fingerprint"]:
            raise RuntimeError(
                f"Place catalog for {region_key} changed while statistics were calculated"
            )

        source_signature["rowCount"] = row_count
        snapshot = self.repository.save_region_snapshot(
            region_key=region_key,
            algorithm_version=ALGORITHM_VERSION,
            source_signature=source_signature,
            regions=regions,
            generated_at=generated_at,
            expires_at=generated_at + timedelta(hours=self.snapshot_ttl_hours),
        )
        return PlannerRegionStatisticsResult(
            status="refreshed",
            region_key=region_key,
            regions=regions,
            snapshot_id=snapshot.id,
            catalog_version=snapshot.catalog_version,
            algorithm_version=snapshot.algorithm_version,
            generated_at=snapshot.generated_at.isoformat(),
            source_fingerprint=str(source_signature["fingerprint"]),
        )

    def _read_existing(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as file:
                value = json.load(file)
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _is_current(
        self,
        existing: dict[str, Any] | None,
        source_signature: dict[str, str | int],
    ) -> bool:
        if not existing:
            return False
        source = existing.get("source", {})
        return (
            existing.get("algorithmVersion") == ALGORITHM_VERSION
            and existing.get("staleAfterDays") == self.stale_after_days
            and source.get("fingerprint") == source_signature["fingerprint"]
        )

    def _atomic_write(self, output: dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(output, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _is_future(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > now
