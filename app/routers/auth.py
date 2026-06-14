from fastapi import APIRouter, Depends
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import errors, services
from ..config import settings
from ..db import get_db
from ..models import (
    EMAIL,
    PURPOSE_LOGIN_2FA,
    PURPOSE_LOGIN_PASSWORDLESS,
    PURPOSE_SIGNUP,
    SMS,
    User,
    VerificationCode,
)
from ..schemas import (
    ChallengeIn,
    IdentifierIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    ResendIn,
    VerifyIn,
)
from ..security import decode_token, hash_secret, make_access, tokens_for, verify_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])
dev_router = APIRouter(prefix="/api/dev", tags=["dev"])


async def find_user(db: AsyncSession, identifier: str) -> User | None:
    stmt = select(User).where(
        or_(User.username == identifier, User.email == identifier, User.phone == identifier)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _exists(db: AsyncSession, field: str, value: str) -> bool:
    col = getattr(User, field)
    return (await db.execute(select(User.id).where(col == value))).first() is not None


@router.post("/register", status_code=201)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    fields = {}
    if not data.email and not data.phone:
        fields["non_field_errors"] = "Provide at least one of email or phone."
    if await _exists(db, "username", data.username):
        fields["username"] = "That username is taken."
    if data.email and await _exists(db, "email", data.email):
        fields["email"] = "That email is already registered."
    if data.phone and await _exists(db, "phone", data.phone):
        fields["phone"] = "That phone is already registered."
    if len(data.password) < 8:
        fields["password"] = "This password is too short. It must contain at least 8 characters."
    if fields:
        raise errors.validation_error(fields)

    user = User(
        username=data.username,
        email=data.email,
        phone=data.phone,
        password_hash=hash_secret(data.password),
        bio="",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    challenges = []
    if user.email:
        challenges.append(await services.issue_code(db, user, channel=EMAIL, purpose=PURPOSE_SIGNUP))
    if user.phone:
        challenges.append(await services.issue_code(db, user, channel=SMS, purpose=PURPOSE_SIGNUP))

    return {
        "user_id": user.id,
        "challenges": [services.challenge_payload(c) for c in challenges],
    }


@router.post("/verify")
async def verify(data: VerifyIn, db: AsyncSession = Depends(get_db)):
    vc = await db.get(VerificationCode, data.challenge_id)
    if not vc:
        raise errors.not_found("Unknown challenge.")
    await services.check_code(db, vc, data.code)
    user = await db.get(User, vc.user_id)

    if vc.purpose == PURPOSE_SIGNUP:
        user.mark_channel_verified(vc.channel)
        await db.commit()
        if user.all_contacts_verified():
            if not user.is_active:
                user.is_active = True
                await db.commit()
            return {"status": "complete", **tokens_for(user.id),
                    "user": services.user_summary(user)}

        stmt = select(VerificationCode).where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == PURPOSE_SIGNUP,
            VerificationCode.consumed_at.is_(None),
        )
        remaining = (await db.execute(stmt)).scalars().all()
        return {
            "status": "pending",
            "remaining": [{"challenge_id": r.id, "channel": r.channel} for r in remaining],
        }

    return {"status": "complete", **tokens_for(user.id), "user": services.user_summary(user)}


@router.post("/login")
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await find_user(db, data.identifier)
    if not user or not verify_secret(data.password, user.password_hash):
        raise errors.invalid_credentials()
    if not user.is_active:
        raise errors.not_verified()
    return {"user_id": user.id, "channels": [{"channel": c} for c in user.verified_channels()]}


@router.post("/login/code")
async def login_code(data: IdentifierIn, db: AsyncSession = Depends(get_db)):
    user = await find_user(db, data.identifier)
    if not user or not user.is_active or not user.verified_channels():
        raise errors.invalid_credentials()
    return {"user_id": user.id, "channels": [{"channel": c} for c in user.verified_channels()]}


@router.post("/challenge", status_code=201)
async def challenge(data: ChallengeIn, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, data.user_id)
    if not user:
        raise errors.not_found("Unknown user.")
    if data.purpose not in (PURPOSE_LOGIN_2FA, PURPOSE_LOGIN_PASSWORDLESS):
        raise errors.validation_error({"purpose": "Invalid purpose."})
    if data.channel not in user.verified_channels():
        raise errors.forbidden("That channel is not verified.")
    vc = await services.issue_code(db, user, channel=data.channel, purpose=data.purpose)
    return services.challenge_payload(vc)


@router.post("/resend", status_code=201)
async def resend(data: ResendIn, db: AsyncSession = Depends(get_db)):
    old = await db.get(VerificationCode, data.challenge_id)
    if not old:
        raise errors.not_found("Unknown challenge.")
    user = await db.get(User, old.user_id)
    vc = await services.issue_code(db, user, channel=old.channel, purpose=old.purpose)
    return services.challenge_payload(vc)


@router.post("/refresh")
async def refresh(data: RefreshIn):
    try:
        payload = decode_token(data.refresh, expected_type="refresh")
    except JWTError:
        raise errors.ContractError("unauthenticated", "Invalid refresh token.", 401)
    return {"access": make_access(payload["user_id"])}


@dev_router.get("/last-code")
async def last_code(challenge_id: int, db: AsyncSession = Depends(get_db)):
    if settings.ENV != "dev":
        raise errors.not_found()
    vc = await db.get(VerificationCode, challenge_id)
    if not vc or not vc.dev_code:
        raise errors.not_found("No code for that challenge.")
    return {"challenge_id": vc.id, "code": vc.dev_code}
