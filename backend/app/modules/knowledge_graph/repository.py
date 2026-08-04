from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from app.core.config import BACKEND_ROOT


class GraphImportRepository:
    _lock = threading.RLock()

    def __init__(self, path: Path = BACKEND_ROOT / "var" / "knowledge-graph-imports.json") -> None:
        self.path = path
        self.directory = path.with_suffix("")
        self.index_path = self.directory / "index.json"

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        with self._lock:
            self._ensure_migrated()
            items = sorted(self._read_index(), key=lambda item: item["created_at"], reverse=True)
            if status:
                items = [item for item in items if item.get("status") == status]
            if search:
                needle = search.strip().lower()
                if needle:
                    items = [
                        item for item in items
                        if needle in str(item.get("source_label", "")).lower()
                        or needle in str(item.get("id", "")).lower()
                    ]
            total = len(items)
            if offset:
                items = items[offset:]
            if limit is not None:
                items = items[:limit]
            return items, total

    def count(self) -> int:
        with self._lock:
            self._ensure_migrated()
            return len(self._read_index())

    def get(self, import_id: str) -> dict | None:
        with self._lock:
            self._ensure_migrated()
            job_path = self.directory / f"{import_id}.json"
            if not job_path.exists():
                return None
            try:
                value = json.loads(job_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            return value if isinstance(value, dict) else None

    def save(self, value: dict) -> dict:
        with self._lock:
            self._ensure_migrated()
            self.directory.mkdir(parents=True, exist_ok=True)
            job_path = self.directory / f"{value['id']}.json"
            self._atomic_write(job_path, value)
            items = [item for item in self._read_index() if item["id"] != value["id"]]
            items.append(self._summary(value))
            self._atomic_write(self.index_path, items)
            return value

    def save_many(self, values: list[dict]) -> None:
        with self._lock:
            self._ensure_migrated()
            self.directory.mkdir(parents=True, exist_ok=True)
            ids = {value["id"] for value in values}
            for value in values:
                self._atomic_write(self.directory / f"{value['id']}.json", value)
            items = [item for item in self._read_index() if item["id"] not in ids]
            items.extend(self._summary(value) for value in values)
            self._atomic_write(self.index_path, items)

    def delete(self, import_id: str) -> bool:
        with self._lock:
            self._ensure_migrated()
            job_path = self.directory / f"{import_id}.json"
            existed = job_path.exists()
            if existed:
                job_path.unlink()
            items = [item for item in self._read_index() if item["id"] != import_id]
            self._atomic_write(self.index_path, items)
            return existed

    def _read_legacy(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return value if isinstance(value, list) else []

    def _read_index(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return value if isinstance(value, list) else []

    def _ensure_migrated(self) -> None:
        legacy_items = self._read_legacy()
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            items = self._read_index()
            indexed_ids = {item.get("id") for item in items}
            changed = False
            for item in legacy_items:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                job_path = self.directory / f"{item['id']}.json"
                if not job_path.exists():
                    self._atomic_write(job_path, item)
                    changed = True
                if item["id"] not in indexed_ids:
                    items.append(self._summary(item))
                    indexed_ids.add(item["id"])
                    changed = True
            if changed:
                self._atomic_write(self.index_path, items)
            return
        for item in legacy_items:
            if isinstance(item, dict) and item.get("id"):
                self._atomic_write(self.directory / f"{item['id']}.json", item)
        self._atomic_write(
            self.index_path,
            [self._summary(item) for item in legacy_items if isinstance(item, dict) and item.get("id")],
        )

    @staticmethod
    def _summary(value: dict) -> dict:
        nodes = value.get("nodes", [])
        edges = value.get("edges", [])
        return {
            "id": value["id"],
            "source_label": value.get("source_label", ""),
            "source_url": value.get("source_url"),
            "status": value.get("status", "failed"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "issue_count": sum(
                len(item.get("validation_issues", []))
                for item in [*nodes, *edges]
                if isinstance(item, dict)
            ),
            "created_at": value.get("created_at", ""),
            "applied_at": value.get("applied_at"),
            "error_message": value.get("error_message"),
        }

    @staticmethod
    def _atomic_write(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(20):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05 * (attempt + 1))
