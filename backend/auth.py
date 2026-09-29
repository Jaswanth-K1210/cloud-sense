"""Email + password accounts with bearer-token sessions (stdlib only).

Passwords: scrypt with a random salt. Sessions: random 32-byte tokens; only their SHA-256 is stored.
"""

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.store.models import AuthSession, User

MIN_PASSWORD = 10
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${salt.hex()}${dk.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, want = stored.split("$")
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P)
    return hmac.compare_digest(dk.hex(), want)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(s: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=_digest(token), user_id=user.id))
    s.flush()
    return token


def user_for_token(s: Session, token: str) -> User | None:
    row = s.get(AuthSession, _digest(token))
    return s.get(User, row.user_id) if row else None


def end_session(s: Session, token: str) -> None:
    row = s.get(AuthSession, _digest(token))
    if row:
        s.delete(row)


def end_all_sessions(s: Session, user: User, keep: str | None = None) -> None:
    keep_hash = _digest(keep) if keep else None
    for row in s.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
        if row.token_hash != keep_hash:
            s.delete(row)
