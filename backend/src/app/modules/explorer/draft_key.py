import hashlib
import json

from app.modules.explorer.contract import ExplorerInput
from app.modules.explorer.models import SourceExtractionResult


EXPLORER_DRAFT_CACHE_VERSION = "3"


def explorer_draft_cache_key(
    payload: ExplorerInput,
    sources: list[SourceExtractionResult],
    *,
    namespace: str,
) -> str:
    normalized_sources = []
    for source in sorted(sources, key=lambda item: item.source_index):
        artifacts = [{
            "type": artifact.artifact_type,
            "text": artifact.text,
            "sourceUrl": artifact.source_url,
            "sourceTimeHint": artifact.source_time_hint,
            "language": artifact.language,
        } for artifact in source.artifacts]
        normalized_sources.append({
            "sourceIndex": source.source_index,
            "sourceKind": source.source_kind,
            "status": source.status,
            "artifacts": artifacts,
        })
    value = json.dumps(
        {
            "version": EXPLORER_DRAFT_CACHE_VERSION,
            "namespace": namespace,
            "rawPrompt": payload.raw_prompt or "",
            "sources": normalized_sources,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()
