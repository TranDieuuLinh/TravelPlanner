from dataclasses import dataclass
from types import MappingProxyType

from pydantic import BaseModel

from app.shared.observability.redaction import (
    is_sensitive_key,
    redact_string,
    safe_preview,
    sanitize_payload,
)


def test_redact_string_masks_api_keys_and_tokens() -> None:
    text = (
        "Using key AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6 and "
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz and "
        "postgres://user:super_secret_pw@db.cloud.example.com:5432/travel_db "
        "and pk-lf-12345678-1234-1234-1234-123456789abc"
    )
    redacted = redact_string(text)

    assert "AIza" not in redacted
    assert "super_secret_pw" not in redacted
    assert "pk-lf-" not in redacted
    assert "Bearer [REDACTED]" in redacted
    assert "[REDACTED]" in redacted


def test_redact_string_truncates_long_strings() -> None:
    long_text = "A" * 500
    truncated = redact_string(long_text, max_chars=100)

    assert len(truncated) < 500
    assert truncated.startswith("A" * 100)
    assert "[truncated 400 chars]" in truncated


def test_is_sensitive_key_matches_common_secrets() -> None:
    assert is_sensitive_key("apiKey")
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("secret")
    assert is_sensitive_key("password")
    assert is_sensitive_key("auth_token")
    assert is_sensitive_key("Authorization")
    assert is_sensitive_key("database_url")
    assert not is_sensitive_key("query")
    assert not is_sensitive_key("prompt")
    assert not is_sensitive_key("destination")


def test_sanitize_payload_masks_nested_dict_and_models() -> None:
    class SubModel(BaseModel):
        token: str
        visible: str

    payload = {
        "user_id": "u123",
        "api_key": "AIzaSyDummyKey12345678901234567890123",
        "nested": {
            "password": "secret_pass_123",
            "search_query": "Hue ancient citadel",
        },
        "model": SubModel(token="secret_token", visible="visible_content"),
    }

    sanitized = sanitize_payload(payload)

    assert sanitized["user_id"] == "u123"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["search_query"] == "Hue ancient citadel"
    assert sanitized["model"]["token"] == "[REDACTED]"
    assert sanitized["model"]["visible"] == "visible_content"


def test_sanitize_payload_handles_circular_references_and_depth() -> None:
    cyclic_dict: dict = {"name": "root"}
    cyclic_dict["self"] = cyclic_dict

    sanitized = sanitize_payload(cyclic_dict, max_depth=3)
    assert sanitized["name"] == "root"
    assert sanitized["self"] == "[CIRCULAR]"


def test_safe_preview_produces_clean_json_or_string() -> None:
    data = {"prompt": "Trip to Danang", "key": "secret"}
    preview = safe_preview(data)
    assert preview is not None
    assert '"prompt": "Trip to Danang"' in preview
    assert '"key": "[REDACTED]"' in preview
    assert "secret" not in preview


def test_sanitize_payload_handles_mappingproxy_inside_dataclass() -> None:
    @dataclass(frozen=True)
    class PreparedState:
        candidates: object

    state = PreparedState(
        candidates=MappingProxyType({"place": {"name": "Hồ Hoàn Kiếm"}})
    )

    assert sanitize_payload(state) == {
        "candidates": {"place": {"name": "Hồ Hoàn Kiếm"}}
    }
