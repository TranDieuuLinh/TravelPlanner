from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


class LocalObservabilityStore:
    """Bounded local diagnostics store persisted as a JSON snapshot."""

    def __init__(self, max_traces: int = 500, storage_path: Path | None = None) -> None:
        self.max_traces = max(50, max_traces)
        self._traces: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = Lock()
        backend_root = Path(__file__).resolve().parents[4]
        self.storage_path = storage_path or backend_root / "logs" / "observability" / "traces.json"
        self._load()

    def start_trace(self, request_id: str, metadata: dict[str, Any]) -> None:
        trace = {
            "id": request_id, "request_id": request_id, "name": "travelplanner.agent.invoke",
            "status": "running", "success": None, "route": None, "started_at": _now(),
            "finished_at": None, "duration_ms": None, "message_length": metadata.get("messageLength", 0),
            "warning_count": 0, "source_count": 0, "has_itinerary": False, "error_code": None,
            "thread_id": metadata.get("threadId"), "observations": [],
            "entry_point": metadata.get("entryPoint", "agent.invoke"),
            "input_preview": _safe_preview(metadata.get("input")),
            "output_preview": None,
        }
        with self._lock:
            self._traces[request_id] = trace
            self._traces.move_to_end(request_id)
            while len(self._traces) > self.max_traces:
                self._traces.popitem(last=False)
            self._persist_locked()

    def complete_trace(self, request_id: str, **values: Any) -> None:
        with self._lock:
            trace = self._traces.get(request_id)
            if trace is None:
                return
            output = values.pop("output", None) if "output" in values else None
            trace.update(values)
            trace["finished_at"] = _now()
            trace["status"] = "success" if values.get("success") else "error"
            if output is not None:
                trace["output_preview"] = _safe_preview(output)
            self._persist_locked()

    def start_observation(self, request_id: str, kind: str, name: str, parent_id: str | None = None, input_value: Any = None) -> str:
        observation_id = uuid4().hex
        observation = {
            "id": observation_id, "trace_id": request_id, "name": name, "kind": kind,
            "status": "running", "start_time": _now(), "end_time": None, "duration_ms": None,
            "error": None, "parent_id": parent_id,
            "input_preview": _safe_preview(input_value),
            "output_preview": None,
        }
        with self._lock:
            trace = self._traces.get(request_id)
            if trace is not None:
                trace["observations"].append(observation)
                self._persist_locked()
        return observation_id

    def finish_observation(self, request_id: str, observation_id: str, error: BaseException | None = None, output_value: Any = None) -> None:
        with self._lock:
            trace = self._traces.get(request_id)
            if trace is None:
                return
            for observation in trace["observations"]:
                if observation["id"] != observation_id:
                    continue
                observation["end_time"] = _now()
                observation["status"] = "error" if error else "success"
                observation["error"] = type(error).__name__ if error else None
                observation["output_preview"] = _safe_preview(output_value) if output_value is not None else None
                observation["duration_ms"] = _duration_ms(observation["start_time"], observation["end_time"])
                self._persist_locked()
                return

    def _load(self) -> None:
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            records = payload.get("traces", [])
            if not isinstance(records, list):
                return
            for trace in records[-self.max_traces:]:
                if isinstance(trace, dict) and isinstance(trace.get("id"), str):
                    self._traces[trace["id"]] = trace
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return

    def _persist_locked(self) -> None:
        payload = {"version": 1, "traces": list(self._traces.values())}
        temporary_path = self.storage_path.with_suffix(".tmp")
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            temporary_path.replace(self.storage_path)
        except OSError:
            # Diagnostics must never make an agent request fail.
            return

    def status(self) -> dict[str, Any]:
        with self._lock:
            traces = list(self._traces.values())
            observations = sum(len(item["observations"]) for item in traces)
            errors = sum(item["status"] == "error" for item in traces)
        return {"configured": True, "reachable": True, "message": "Local observability đang hoạt động trong backend process.", "trace_count": len(traces), "observation_count": observations, "error_count": errors, "retention_limit": self.max_traces}

    def page(
        self,
        resource: str,
        page: int,
        limit: int,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if resource == "traces":
                records = [_public_trace(item) for item in reversed(self._traces.values())]
            elif resource == "observations":
                records = [
                    _public_observation(observation)
                    for trace in reversed(self._traces.values())
                    if trace_id is None or trace["id"] == trace_id
                    for observation in reversed(trace["observations"])
                ]
            else:
                records = self._sessions()
        start = (page - 1) * limit
        return {"items": records[start:start + limit], "page": page, "limit": limit, "total": len(records), "has_more": start + limit < len(records)}

    def trace(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return None
            result = _public_trace(trace)
            result["observations"] = [_public_observation(item) for item in trace["observations"]]
            return result

    def _sessions(self) -> list[dict[str, Any]]:
        grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for trace in reversed(self._traces.values()):
            session_id = trace.get("thread_id") or "no-thread"
            session = grouped.setdefault(session_id, {"id": session_id, "trace_count": 0, "error_count": 0, "first_timestamp": trace["started_at"], "last_timestamp": trace["started_at"]})
            session["trace_count"] += 1
            session["error_count"] += trace["status"] == "error"
            session["first_timestamp"] = min(session["first_timestamp"], trace["started_at"])
            session["last_timestamp"] = max(session["last_timestamp"], trace["started_at"])
        return [_camelize(item) for item in grouped.values()]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(start: str, end: str) -> float:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() * 1000, 2)


def _safe_preview(value: Any, max_length: int = 4000) -> str | None:
    if value is None:
        return None
    import json
    redacted = _redact(value)
    try:
        text = redacted if isinstance(redacted, str) else json.dumps(redacted, ensure_ascii=False, default=str, indent=2)
    except (TypeError, ValueError):
        text = str(redacted)
    return text if len(text) <= max_length else text[:max_length] + "… [truncated]"


def _redact(value: Any) -> Any:
    sensitive = {"authorization", "api_key", "apikey", "password", "secret", "token", "cookie"}
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower().replace("-", "_") in sensitive else _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _public_trace(trace: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in trace.items() if key != "observations"}
    public["observation_count"] = len(trace.get("observations", []))
    return _camelize(public)


def _public_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return _camelize(observation)


def _camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {_camel_key(key): _camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _camel_key(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
