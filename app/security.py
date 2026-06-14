import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

# pbkdf2_sha256 is pure-python — no bcrypt version pitfalls. Used for passwords AND codes.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ALGORITHM = "HS256"


def hash_secret(raw: str) -> str:
    return _pwd.hash(raw)


def verify_secret(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def _make_token(user_id: int, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def make_access(user_id: int) -> str:
    return _make_token(user_id, "access", timedelta(minutes=settings.JWT_ACCESS_TTL_MIN))


def make_refresh(user_id: int) -> str:
    return _make_token(user_id, "refresh", timedelta(days=settings.JWT_REFRESH_TTL_DAYS))


def tokens_for(user_id: int) -> dict:
    return {"access": make_access(user_id), "refresh": make_refresh(user_id)}


def decode_token(token: str, expected_type: str) -> dict:
    """Decode and validate; raises JWTError on any problem (incl. wrong type)."""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise JWTError("wrong token type")
    return payload
