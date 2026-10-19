"""Солёные хеши Argon2id; исходные пароли не сохраняются."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher()
_dummy_hash = password_hasher.hash("dummy-password-for-unknown-login")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        valid = password_hasher.verify(encoded or _dummy_hash, password)
        return bool(encoded) and valid
    except (VerificationError, InvalidHashError):
        return False
