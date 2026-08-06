from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_kg_theme_selector_evaluation_is_offline_and_passes(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[3]
    output = tmp_path / "theme-selector-evaluation.json"
    result = subprocess.run(
        [sys.executable, "scripts/evaluate_kg_theme_selector.py", "--output", str(output)],
        cwd=backend,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["scenarios"]["hanoi_culture_food"]["passed"] is True
    assert report["scenarios"]["group_suitability"]["passed"] is True
    assert report["scenarios"]["timing_fill"]["passed"] is True
    assert report["regression"]["food_heavy_plan"]["detected"] is True
    assert "rawPrompt" not in output.read_text(encoding="utf-8")
    assert "providerPayload" not in output.read_text(encoding="utf-8")
