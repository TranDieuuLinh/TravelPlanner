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


class YamlTagCatalog:
    """Read the editable Explorer tag taxonomy on every operation."""

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

    def definitions(self) -> dict[str, list[str]]:
        return self._read_definitions()

    def tags_for(self, value: str) -> list[str]:
        return self._tags_for(value, self.definitions())

    @staticmethod
    def _tags_for(value: str, definitions: dict[str, list[str]]) -> list[str]:
        normalized_value = f" {_normalized_words(value)} "
        return [
            tag
            for tag, keywords in definitions.items()
            if _normalized_words(tag) == _normalized_words(value)
            or any(
                f" {_normalized_words(keyword)} " in normalized_value
                for keyword in keywords
            )
        ]

    def resolve(self, values: list[str]) -> list[str]:
        definitions = self.definitions()
        return list(dict.fromkeys(
            tag
            for value in values
            for tag in self._tags_for(value, definitions)
        ))

    def filter_allowed(self, values: list[str]) -> list[str]:
        allowed = set(self.definitions())
        return list(dict.fromkeys(value for value in values if value in allowed))

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


# Compatibility for callers created before tags were limited to trip preferences.
YamlPlaceTagCatalog = YamlTagCatalog
