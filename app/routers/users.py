from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import errors
from ..db import get_db
from ..deps import get_current_user
from ..models import Follow, User
from ..schemas import MeOut, PublicUserOut

router = APIRouter(prefix="/api/users", tags=["users"])


async def _counts(db: AsyncSession, user_id: int) -> tuple[int, int]:
    followers = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.followed_id == user_id)
    )
    following = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    return followers, following


async def _active_user(db: AsyncSession, username: str) -> User:
    stmt = select(User).where(User.username == username, User.is_active.is_(True))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise errors.not_found("No such user.")
    return user


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    followers, following = await _counts(db, user.id)
    return MeOut(
        id=user.id, username=user.username, email=user.email, phone=user.phone, bio=user.bio,
        email_verified=user.email_verified, phone_verified=user.phone_verified,
        followers_count=followers, following_count=following, created_at=user.created_at,
    )


@router.get("/{username}", response_model=PublicUserOut)
async def profile(
    username: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _active_user(db, username)
    followers, following = await _counts(db, target.id)
    is_following = (
        await db.execute(
            select(Follow.id).where(Follow.follower_id == user.id, Follow.followed_id == target.id)
        )
    ).first() is not None
    return PublicUserOut(
        id=target.id, username=target.username, bio=target.bio,
        followers_count=followers, following_count=following,
        is_following=is_following, created_at=target.created_at,
    )


@router.post("/{username}/follow", status_code=201)
async def follow(
    username: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _active_user(db, username)
    if target.id == user.id:
        raise errors.validation_error({"detail": "You cannot follow yourself."})
    exists = (
        await db.execute(
            select(Follow.id).where(Follow.follower_id == user.id, Follow.followed_id == target.id)
        )
    ).first()
    if not exists:
        db.add(Follow(follower_id=user.id, followed_id=target.id))
        await db.commit()
    followers, _ = await _counts(db, target.id)
    return {"is_following": True, "followers_count": followers}


@router.delete("/{username}/follow")
async def unfollow(
    username: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await _active_user(db, username)
    await db.execute(
        Follow.__table__.delete().where(
            Follow.follower_id == user.id, Follow.followed_id == target.id
        )
    )
    await db.commit()
    followers, _ = await _counts(db, target.id)
    return {"is_following": False, "followers_count": followers}
