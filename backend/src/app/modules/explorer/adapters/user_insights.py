import hashlib
import os
from pathlib import Path
import random

import yaml

from app.modules.explorer.ports import TagCatalog


_BUDGET_GROUP = {
    "low": "tiết_kiệm",
    "medium": "trung_bình",
    "high": "cao_cấp",
}


class YamlInsightCatalog:
    """Project editable user-insight groups into canonical trip tags."""

    def __init__(
        self,
        tag_catalog: TagCatalog,
        path: str | Path | None = None,
    ) -> None:
        self.tag_catalog = tag_catalog
        self.path = Path(path).expanduser() if path else self._default_path()

    @staticmethod
    def _default_path() -> Path:
        configured = os.getenv("EXPLORER_INSIGHT_USER_PATH")
        if configured:
            return Path(configured).expanduser()
        candidates = [
            parent / "auto-attach" / "insight-user.yml"
            for parent in Path(__file__).resolve().parents
        ]
        candidates.append(Path("/auto-attach/insight-user.yml"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            "Cannot find auto-attach/insight-user.yml; "
            "set EXPLORER_INSIGHT_USER_PATH."
        )

    def enrich(
        self,
        *,
        budget_level: str,
        children: int,
        infants: int,
        preferences: list[str],
        avoids: list[str],
        seed: str,
    ) -> tuple[list[str], list[str]]:
        catalog = self._read()
        groups = [catalog["ngân_sách"][_BUDGET_GROUP[budget_level]]]
        if children or infants:
            groups.append(catalog["đối_tượng"]["gia_đình_có_trẻ_em"])

        priority = self.tag_catalog.filter_allowed(
            [tag for group in groups for tag in group["priority-tags"]]
        )
        derived_avoids = self.tag_catalog.filter_allowed(
            [tag for group in groups for tag in group["avoid-tags"]]
        )
        merged_avoids = list(dict.fromkeys([*avoids, *derived_avoids]))
        selected = self.tag_catalog.filter_allowed(preferences)
        selected = [tag for tag in selected if tag not in merged_avoids]

        candidates = [
            tag
            for tag in dict.fromkeys(priority)
            if tag not in selected and tag not in merged_avoids
        ]
        missing = max(0, 4 - len(selected))
        if missing and candidates:
            first = candidates.pop(0)
            additions = [first]
            if missing > 1 and candidates:
                digest = hashlib.sha256(seed.encode("utf-8")).digest()
                rng = random.Random(int.from_bytes(digest[:8], "big"))
                additions.extend(rng.sample(candidates, min(missing - 1, len(candidates))))
            selected.extend(additions[:missing])
        return selected[:4], merged_avoids

    def _read(self) -> dict:
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("insight-user.yml must contain insight groups.")
        for dimension in ("đối_tượng", "ngân_sách", "sở_thích"):
            groups = raw.get(dimension)
            if not isinstance(groups, dict):
                raise ValueError(f"insight-user.yml is missing {dimension!r} groups.")
            for name, group in groups.items():
                if not isinstance(group, dict):
                    raise ValueError(f"Insight group {name!r} must be an object.")
                for field in ("priority-tags", "avoid-tags"):
                    values = group.get(field)
                    if not isinstance(values, list) or not all(
                        isinstance(value, str) and value.strip() for value in values
                    ):
                        raise ValueError(
                            f"Insight group {name!r}.{field} must be a tag list."
                        )
        return raw
