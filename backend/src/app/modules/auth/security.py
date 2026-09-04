import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


def password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return base64.urlsafe_b64encode(digest).decode("ascii")


def new_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16)
    return password_hash(password, salt), base64.urlsafe_b64encode(salt).decode("ascii")


def verify_password(password: str, expected_hash: str, encoded_salt: str) -> bool:
    salt = base64.urlsafe_b64decode(encoded_salt)
    return hmac.compare_digest(password_hash(password, salt), expected_hash)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_jwt(
    *, subject: int, token_type: str, secret: str, ttl_seconds: int, role: str
) -> str:
    """Create a compact HS256 JWT without adding a runtime dependency."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(subject),
        "type": token_type,
        "role": role,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    encoded = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}.{_b64(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(
        secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64(signature)}"


def decode_jwt(token: str, *, secret: str, expected_type: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        encoded = f"{parts[0]}.{parts[1]}"
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_unb64(parts[2]), expected):
            return None
        header = json.loads(_unb64(parts[0]))
        payload = json.loads(_unb64(parts[1]))
        if header.get("alg") != "HS256" or payload.get("type") != expected_type:
            return None
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if not str(payload.get("sub", "")).isdigit():
            return None
        return payload
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeError,
    ):
        return None
