from __future__ import annotations

import hashlib
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
        prefer_snapshot_for_planner: bool = False,
    ) -> None:
        if stale_after_days < 1:
            raise ValueError("stale_after_days must be at least 1")
        self.repository = repository
        self.output_path = output_path.resolve()
        self.stale_after_days = stale_after_days
        self.prefer_snapshot_for_planner = prefer_snapshot_for_planner

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
        if self.prefer_snapshot_for_planner and not force:
            snapshot = self._read_planner_snapshot(region_key)
            if snapshot is not None:
                return snapshot

        source_signature = self.repository.source_signature(region_key)
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
        fingerprint = str(source_signature["fingerprint"])
        return PlannerRegionStatisticsResult(
            status="computed",
            region_key=region_key,
            regions=regions,
            snapshot_id=f"live-{fingerprint[:24]}",
            catalog_version=int(
                hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:15],
                16,
            ),
            algorithm_version=ALGORITHM_VERSION,
            generated_at=generated_at.isoformat(),
            source_fingerprint=fingerprint,
        )

    def _read_planner_snapshot(
        self,
        region_key: str,
    ) -> PlannerRegionStatisticsResult | None:
        existing = self._read_existing(self.output_path)
        if not existing or existing.get("algorithmVersion") != ALGORITHM_VERSION:
            return None

        generated_at_text = existing.get("generatedAt")
        if not isinstance(generated_at_text, str):
            return None
        try:
            generated_at = datetime.fromisoformat(
                generated_at_text.replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        if utc_now() - generated_at > timedelta(days=self.stale_after_days):
            return None

        all_regions = existing.get("regions")
        if not isinstance(all_regions, list):
            return None
        regions = [
            region
            for region in all_regions
            if isinstance(region, dict)
            and isinstance(region.get("regionKey"), str)
            and (
                region["regionKey"] == region_key
                or region["regionKey"].startswith(f"{region_key},")
                or region["regionKey"].startswith(f"{region_key}:")
            )
        ]
        if not any(region.get("regionKey") == region_key for region in regions):
            return None

        source = existing.get("source")
        if not isinstance(source, dict):
            return None
        fingerprint = source.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            return None

        return PlannerRegionStatisticsResult(
            status="snapshot",
            region_key=region_key,
            regions=regions,
            snapshot_id=f"snapshot-{fingerprint[:24]}",
            catalog_version=int(
                hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:15],
                16,
            ),
            algorithm_version=str(existing["algorithmVersion"]),
            generated_at=generated_at.isoformat(),
            source_fingerprint=fingerprint,
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
