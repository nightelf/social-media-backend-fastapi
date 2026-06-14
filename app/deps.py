from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import errors
from .db import get_db
from .models import User
from .security import decode_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise errors.ContractError("unauthenticated", "Authentication required.", 401)
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token, expected_type="access")
    except JWTError:
        raise errors.ContractError("unauthenticated", "Invalid or expired token.", 401)

    user = await db.get(User, payload.get("user_id"))
    if not user or not user.is_active:
        raise errors.ContractError("unauthenticated", "Authentication required.", 401)
    return user


class Pagination:
    """Mirrors the contract's ?page & ?page_size with the same defaults/limits."""

    def __init__(self, page: int = 1, page_size: int = 20):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
