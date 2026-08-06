from __future__ import annotations

import asyncio
import json
import os
import signal
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import BACKEND_ROOT

from .base import WebSearchResult


class GooglePlaywrightSearchProvider:
    """Run bounded Google web searches through the isolated Playwright adapter."""

    provider_name = "google_playwright"

    def __init__(
        self,
        *,
        work_dir: Path | None = None,
        timeout_seconds: float = 60.0,
        min_interval_seconds: float = 8.0,
        node_executable: str = "node",
        script_path: Path | None = None,
    ) -> None:
        self.work_dir = work_dir if work_dir and work_dir.exists() else None
        self.timeout_seconds = max(5.0, timeout_seconds)
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.node_executable = node_executable
        self.script_path = script_path or (
            BACKEND_ROOT / "scripts" / "google_web_search.js"
        )
        self._interval_lock = asyncio.Lock()
        self._last_search_started_at = 0.0

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []
        await self._wait_for_interval()
        raw_results = (
            await self._search_via_worker(cleaned, limit)
            if self.work_dir is not None
            else await self._search_via_local_node(cleaned, limit)
        )
        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for item in raw_results:
            uri = str(item.get("uri") or "").strip()
            parsed = urlsplit(uri)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            if uri in seen:
                continue
            seen.add(uri)
            results.append(
                WebSearchResult(
                    title=str(item.get("title") or uri).strip()[:500],
                    uri=uri[:2048],
                    snippet=str(item.get("snippet") or "").strip()[:2000],
                )
            )
            if len(results) >= max(1, min(limit, 10)):
                break
        return results

    async def _wait_for_interval(self) -> None:
        async with self._interval_lock:
            remaining = (
                self._last_search_started_at + self.min_interval_seconds
                - time.monotonic()
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_search_started_at = time.monotonic()

    async def _search_via_local_node(
        self,
        query: str,
        limit: int,
    ) -> list[dict]:
        env = dict(os.environ)
        local_node_modules = BACKEND_ROOT / "playwright-worker" / "node_modules"
        current_node_path = env.get("NODE_PATH")
        env["NODE_PATH"] = (
            f"{local_node_modules}{os.pathsep}{current_node_path}"
            if current_node_path
            else str(local_node_modules)
        )
        process = await asyncio.create_subprocess_exec(
            self.node_executable,
            str(self.script_path),
            "--query",
            query,
            "--limit",
            str(max(1, min(limit, 10))),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.communicate()
            raise RuntimeError("google_playwright_timeout")
        if process.returncode != 0:
            error_code = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(error_code[:200] or "google_playwright_failed")
        return _decode_results(stdout.decode("utf-8", errors="replace"))

    async def _search_via_worker(
        self,
        query: str,
        limit: int,
    ) -> list[dict]:
        if self.work_dir is None:
            return []
        directories = {
            name: self.work_dir / name
            for name in ("requests", "responses", "errors", "cancellations")
        }
        for directory in directories.values():
            directory.mkdir(parents=True, exist_ok=True)
        job_id = f"web-{uuid.uuid4().hex}"
        request_path = directories["requests"] / f"{job_id}.json"
        response_path = directories["responses"] / f"{job_id}.json"
        error_path = directories["errors"] / f"{job_id}.txt"
        cancellation_path = directories["cancellations"] / f"{job_id}.cancel"
        now_ms = int(time.time() * 1000)
        payload = {
            "kind": "google_web_search",
            "query": query,
            "limit": max(1, min(limit, 10)),
            "createdAtMs": now_ms,
            "deadlineAtMs": now_ms + int(self.timeout_seconds * 1000),
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directories["requests"],
            prefix=f".{job_id}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False)
            temporary_path = Path(handle.name)
        temporary_path.replace(request_path)
        deadline = time.monotonic() + self.timeout_seconds
        try:
            while time.monotonic() < deadline:
                if response_path.exists():
                    payload = json.loads(response_path.read_text(encoding="utf-8"))
                    return list(payload.get("results") or [])
                if error_path.exists():
                    raise RuntimeError(
                        error_path.read_text(encoding="utf-8").strip()
                        or "google_playwright_failed"
                    )
                await asyncio.sleep(0.2)
            cancellation_path.write_text("cancel\n", encoding="utf-8")
            raise RuntimeError("google_playwright_timeout")
        finally:
            request_path.unlink(missing_ok=True)
            response_path.unlink(missing_ok=True)
            error_path.unlink(missing_ok=True)


def _decode_results(value: str) -> list[dict]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("google_playwright_invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RuntimeError("google_playwright_invalid_payload")
    return list(payload["results"])
