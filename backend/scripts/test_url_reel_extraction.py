from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.plans.explorer.tools.url_reels.schema import UrlReelInput
from app.modules.plans.explorer.tools.url_reels.service import UrlReelExtractionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test URL reel STT extraction.")
    parser.add_argument("url", help="TikTok/Instagram/YouTube URL to test")
    parser.add_argument("--destination", default=None, help="Optional destination context, e.g. Hanoi")
    parser.add_argument("--work-dir", default="/tmp/vsf_url_reel_test", help="Directory for temporary artifacts")
    parser.add_argument("--stt-language", default="en,vi", help="Optional STT language hint, e.g. en, vi, or en,vi")
    parser.add_argument("--stt-initial-prompt", default=None, help="Optional STT vocabulary/context hint")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = UrlReelInput(
        url=args.url,
        destination=args.destination,
        workDir=Path(args.work_dir),
        sttLanguage=args.stt_language,
        sttInitialPrompt=args.stt_initial_prompt,
    )
    result = UrlReelExtractionService().extract(payload)
    data = result.model_dump(mode="json", by_alias=True)
    result_path = Path(args.work_dir) / "url_reel_result.json"
    result_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Timings ===")
    for key, value in data["timings"].items():
        print(f"{key}: {value:.2f}s")

    print("\n=== Extracted Context ===")
    print(json.dumps(data["extractedContext"], indent=2, ensure_ascii=False))

    print("\n=== Upload Fallback ===")
    print(f"needsImageUpload: {data['needsImageUpload']}")

    print("\n=== Speech To Text ===")
    stt = data["speechToText"]
    print(f"status: {stt.get('status', 'unknown')}")
    if stt.get("error"):
        print(f"error: {stt['error']}")

    print("\n=== Transcript Preview ===")
    transcript = stt.get("text") or ""
    print(transcript[:1500] if transcript else "[empty transcript]")

    print("\n=== Artifacts ===")
    print(f"video: {data['artifacts']['videoPath']}")
    print(f"audio: {data['artifacts']['audioPath']}")
    print(f"result: {result_path}")


if __name__ == "__main__":
    main()
