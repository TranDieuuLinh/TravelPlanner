from collections.abc import Callable

from app.modules.explorer.models import AdmEvidence, ExplorerDraft


def _evidence_count(values: list[AdmEvidence]) -> int:
    return len({
        (
            item.source_url or "",
            item.source_type.casefold().strip(),
            " ".join(item.evidence.casefold().split()),
        )
        for item in values
    })


def _group_score(values: list[AdmEvidence]) -> tuple[float, int]:
    return max(item.confidence for item in values), _evidence_count(values)


def reconcile_adm_candidates(
    draft: ExplorerDraft,
    *,
    normalize_key: Callable[[str], str],
) -> tuple[str | None, bool]:
    candidates = [item for item in draft.adm_candidates if item.confidence >= 0.7]
    if not candidates and draft.input_adm:
        return draft.input_adm.strip(), False

    groups: dict[str, list[AdmEvidence]] = {}
    for candidate in candidates:
        groups.setdefault(normalize_key(candidate.value), []).append(candidate)

    if len(groups) > 1:
        scores = {key: _group_score(values) for key, values in groups.items()}
        strong_keys = [key for key, score in scores.items() if score[0] >= 0.9]
        if len(strong_keys) > 1:
            primary_key = normalize_key(draft.input_adm) if draft.input_adm else None
            primary_score = scores.get(primary_key or "")
            competing_score = max(
                (score for key, score in scores.items() if key != primary_key),
                default=(-1, 0),
            )
            if primary_score is None or primary_score <= competing_score:
                return None, True

    if not groups:
        return None, False
    best = max(
        groups.values(),
        key=_group_score,
    )
    return max(best, key=lambda item: item.confidence).value.strip(), False
