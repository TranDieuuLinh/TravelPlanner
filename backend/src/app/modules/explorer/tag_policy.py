import json

from pydantic import ValidationError

from app.modules.explorer.models import ExplorerDraft


class InvalidDraftTags(ValueError):
    pass


def taxonomy_prompt(definitions: dict[str, list[str]]) -> str:
    serialized = json.dumps(definitions, ensure_ascii=False, separators=(",", ":"))
    return f"""

TAG TAXONOMY (authoritative runtime data):
{serialized}

For short_preferences and short_avoids:
- Select only exact tag keys from TAG TAXONOMY, preserving spelling and case.
- short_preferences contains positive interests; short_avoids contains dislikes.
- Use the keyword lists only as semantic guidance. Output tag keys, never keywords.
- Infer a tag only when the user's raw prompt supports it.
- Return an empty list when no tag matches. Never invent or translate a tag key.
"""


def draft_schema_with_tag_enum(allowed_tags: list[str]) -> dict:
    schema = ExplorerDraft.model_json_schema()
    for field in ("shortPreferences", "shortAvoids"):
        items = schema["properties"][field]["items"]
        items["enum"] = allowed_tags
    return schema


def provider_schema(value):
    if isinstance(value, dict):
        return {
            key: provider_schema(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [provider_schema(item) for item in value]
    return value


def validate_draft_tags(draft: ExplorerDraft, allowed_tags: list[str]) -> None:
    allowed = set(allowed_tags)
    invalid = [
        value
        for values in (draft.short_preferences, draft.short_avoids)
        for value in values
        if value not in allowed
    ]
    if invalid:
        raise InvalidDraftTags(
            "Gemini returned tags outside tags-auto.yml: "
            + ", ".join(dict.fromkeys(invalid))
        )


def parse_tagged_draft(raw: str, allowed_tags: list[str]) -> ExplorerDraft:
    try:
        draft = ExplorerDraft.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidDraftTags("Gemini returned an invalid ExplorerDraft.") from exc
    validate_draft_tags(draft, allowed_tags)
    return draft
