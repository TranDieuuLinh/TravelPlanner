import os
from pathlib import Path
import unicodedata

import yaml


def _normalized_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized)
        .split()
    )


class YamlPlaceTagCatalog:
    """Read the editable tag dictionary for every public Explorer response."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else self._default_path()

    @staticmethod
    def _default_path() -> Path:
        configured = os.getenv("EXPLORER_TAGS_AUTO_PATH")
        if configured:
            return Path(configured).expanduser()

        candidates = [
            parent / "auto-attach" / "tags-auto.yml"
            for parent in Path(__file__).resolve().parents
        ]
        candidates.append(Path("/auto-attach/tags-auto.yml"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            "Cannot find auto-attach/tags-auto.yml; set EXPLORER_TAGS_AUTO_PATH."
        )

    def tags_for(self, place_name: str) -> list[str]:
        definitions = self._read_definitions()
        normalized_name = f" {_normalized_words(place_name)} "
        return [
            tag
            for tag, keywords in definitions.items()
            if any(
                f" {_normalized_words(keyword)} " in normalized_name
                for keyword in keywords
            )
        ]

    def _read_definitions(self) -> dict[str, list[str]]:
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("tags-auto.yml must contain a tag-to-keywords mapping.")

        definitions: dict[str, list[str]] = {}
        for tag, keywords in raw.items():
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("Every tags-auto.yml key must be a non-empty string.")
            if not isinstance(keywords, list) or not all(
                isinstance(keyword, str) and keyword.strip() for keyword in keywords
            ):
                raise ValueError(
                    f"Tag {tag!r} must map to a list of non-empty keywords."
                )
            definitions[tag] = keywords
        return definitions
