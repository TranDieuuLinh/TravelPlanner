from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_LOG = (
    Path(__file__).resolve().parents[1]
    / "var"
    / "explorer-timings.jsonl"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show one Explorer timing report from the JSONL log."
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG,
    )
    parser.add_argument("--intake-id")
    args = parser.parse_args()

    reports = _read_reports(args.log_file)
    if args.intake_id:
        reports = [
            report
            for report in reports
            if report.get("intakeId") == args.intake_id
        ]
    if not reports:
        raise SystemExit("Không tìm thấy Explorer timing report phù hợp.")

    _print_report(reports[-1])


def _read_reports(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Timing log chưa tồn tại: {path}")
    reports: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            reports.append(value)
    return reports


def _print_report(report: dict[str, Any]) -> None:
    print(
        f"Explorer {report.get('intakeId')} · "
        f"{report.get('status')} · "
        f"{report.get('totalSeconds', 0):.3f}s"
    )
    print(
        f"Candidates {report.get('candidateCount', 0)} · "
        f"resolved {report.get('resolvedCount', 0)} · "
        f"persisted {report.get('persistedCount', 0)}"
    )
    provider_counts = report.get("providerCounts", {})
    if provider_counts:
        print(
            "Providers "
            + " · ".join(
                f"{provider} {count}"
                for provider, count in provider_counts.items()
            )
        )
    attempts = report.get("providerAttempts", [])
    if attempts:
        print("Provider attempts")
        for attempt in attempts:
            reason = attempt.get("rejectionReason")
            suffix = f" · {reason}" if reason else ""
            print(
                f"  {attempt.get('candidate')} · {attempt.get('provider')} · "
                f"{attempt.get('aliasQueryCount', 0)} query · "
                f"queue {attempt.get('queueWaitSeconds', 0):.3f}s · "
                f"run {attempt.get('executionSeconds', 0):.3f}s · "
                f"{attempt.get('outcome')}{suffix}"
            )
    for stage in report.get("stages", []):
        print(
            f"  {stage.get('label', stage.get('key'))}: "
            f"{stage.get('durationSeconds', 0):.3f}s"
        )
    for source in report.get("sources", []):
        print(
            f"  URL {source.get('sourceIndex')} "
            f"({source.get('platform')}): "
            f"{source.get('totalSeconds', 0):.3f}s"
        )
        for stage in source.get("stages", []):
            print(
                f"    {stage.get('label', stage.get('key'))}: "
                f"{stage.get('durationSeconds', 0):.3f}s"
            )


if __name__ == "__main__":
    main()
