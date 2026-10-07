"""Password hashing with bcrypt directly.

passlib 1.7.4 (unmaintained) breaks against bcrypt >= 4.1 (fresh installs pull
bcrypt 5.x, where every hash raises ``ValueError: password cannot be longer
than 72 bytes``). stdlib-free direct bcrypt keeps the exact same ``$2b$``
hash format, so all existing password hashes keep verifying.
"""

import bcrypt

_BCRYPT_MAX_BYTES = 72


def _to_bytes(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long (bcrypt supports at most 72 bytes).")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Over-long candidate or malformed stored hash: cannot match.
        return False
