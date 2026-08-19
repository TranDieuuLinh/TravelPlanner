import base64
import hashlib
import hmac
import os


def password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
    )
    return base64.urlsafe_b64encode(digest).decode("ascii")


def new_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16)
    return password_hash(password, salt), base64.urlsafe_b64encode(salt).decode("ascii")


def verify_password(password: str, expected_hash: str, encoded_salt: str) -> bool:
    salt = base64.urlsafe_b64decode(encoded_salt)
    return hmac.compare_digest(password_hash(password, salt), expected_hash)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
