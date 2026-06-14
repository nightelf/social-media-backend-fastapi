from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, EmailStr, PlainSerializer

# Serialize datetimes as UTC with a trailing "Z" (matches the Django/DRF output exactly).
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(
        lambda dt: dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        return_type=str,
    ),
]


# ---- request bodies ----
class RegisterIn(BaseModel):
    username: str
    email: EmailStr | None = None
    phone: str | None = None
    password: str


class VerifyIn(BaseModel):
    challenge_id: int
    code: str


class LoginIn(BaseModel):
    identifier: str
    password: str


class IdentifierIn(BaseModel):
    identifier: str


class ChallengeIn(BaseModel):
    user_id: int
    channel: str
    purpose: str = "LOGIN_2FA"


class ResendIn(BaseModel):
    challenge_id: int


class RefreshIn(BaseModel):
    refresh: str


class PostIn(BaseModel):
    body: str


class CommentIn(BaseModel):
    body: str


# ---- response models ----
class AuthorOut(BaseModel):
    id: int
    username: str


class MeOut(BaseModel):
    id: int
    username: str
    email: str | None
    phone: str | None
    bio: str
    email_verified: bool
    phone_verified: bool
    followers_count: int
    following_count: int
    created_at: UTCDateTime


class PublicUserOut(BaseModel):
    id: int
    username: str
    bio: str
    followers_count: int
    following_count: int
    is_following: bool
    created_at: UTCDateTime


class PostOut(BaseModel):
    id: int
    body: str
    author: AuthorOut
    like_count: int
    comment_count: int
    liked_by_me: bool
    created_at: UTCDateTime


class CommentOut(BaseModel):
    id: int
    body: str
    author: AuthorOut
    created_at: UTCDateTime
