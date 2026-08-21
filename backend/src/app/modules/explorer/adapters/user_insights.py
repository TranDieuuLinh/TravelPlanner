import os
from pathlib import Path

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
        # Keep the port-compatible argument, but never use it to sample tags.
        catalog = self._read()
        groups = [catalog["ngân_sách"][_BUDGET_GROUP[budget_level]]]
        if children or infants:
            groups.append(catalog["đối_tượng"]["gia_đình_có_trẻ_em"])

        insight_tags = set(
            self.tag_catalog.filter_allowed(self._declared_tags(catalog))
        )
        priority = [
            tag
            for tag in self.tag_catalog.filter_allowed(
                [tag for group in groups for tag in group["priority-tags"]]
            )
            if tag in insight_tags
        ]
        derived_avoids = [
            tag
            for tag in self.tag_catalog.filter_allowed(
                [tag for group in groups for tag in group["avoid-tags"]]
            )
            if tag in insight_tags
        ]
        supplied_avoids = [
            tag
            for tag in self.tag_catalog.filter_allowed(avoids)
            if tag in insight_tags
        ]
        merged_avoids = list(dict.fromkeys([*supplied_avoids, *derived_avoids]))
        selected = [
            tag
            for tag in self.tag_catalog.filter_allowed(preferences)
            if tag in insight_tags
        ]
        selected = [tag for tag in selected if tag not in merged_avoids]
        selected.extend(
            tag
            for tag in priority
            if tag not in selected and tag not in merged_avoids
        )
        return selected, merged_avoids

    @staticmethod
    def _declared_tags(catalog: dict) -> list[str]:
        return list(
            dict.fromkeys(
                tag
                for dimension in ("đối_tượng", "ngân_sách", "sở_thích")
                for group in catalog[dimension].values()
                for field in ("priority-tags", "avoid-tags")
                for tag in group[field]
            )
        )

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
