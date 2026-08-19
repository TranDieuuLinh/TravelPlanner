import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.modules.information_finder.answering import validate_and_render_answer
from app.modules.information_finder.contract import (
    AnswerClaim,
    GeneratedAnswer,
    RetrievedSource,
)
from app.modules.information_finder.prompts import (
    ANSWER_SYSTEM_PROMPT,
    build_answer_prompt,
)

CASES_PATH = Path(__file__).parents[1] / "evals" / "cases.json"
NOW = datetime.now(timezone.utc)


def test_deterministic_eval_cases_enforce_answer_invariants():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert {case["id"] for case in cases} >= {
        "vi-opening-hours",
        "en-ticket-price",
        "conflicting-hours",
        "missing-source",
        "cross-lingual",
        "prompt-injection-source",
    }
    for case in cases:
        sources = [
            RetrievedSource(
                source_id=item["id"],
                snapshot_id=f"snap-{item['id']}",
                title=item["id"],
                url=f"https://example.test/{item['id']}",
                content=item["content"],
                last_fetched_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
            for item in case["sources"]
        ]
        prompt = build_answer_prompt(
            case["query"],
            sources,
            max_chars_per_source=4000,
            max_total_source_chars=12000,
        )
        assert case["query"] in prompt
        if not sources:
            assert case["claim"] is None
            continue
        generated = GeneratedAnswer(
            claims=[AnswerClaim(text=case["claim"], source_ids=case["sourceIds"])]
        )
        answer, _, cited = validate_and_render_answer(generated, sources)
        assert all(term in answer for term in case["requiredTerms"])
        assert [item.source_id for item in cited] == list(
            dict.fromkeys(case["sourceIds"])
        )
        assert "[1]" in answer
    assert "không đáng tin cậy" in " ".join(ANSWER_SYSTEM_PROMPT.split())
