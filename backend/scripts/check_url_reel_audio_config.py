from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings


def main() -> None:
    if not settings.gemini_stt_key_pool:
        raise SystemExit(
            "GEMINI_STT_API_KEYS or GEMINI_API_KEY is missing."
        )
    print(f"Gemini audio model configured: {settings.gemini_audio_model}")


if __name__ == "__main__":
    main()
