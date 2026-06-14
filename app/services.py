"""Auth domain logic shared by the auth router: code issue/verify, masking."""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from . import errors
from .config import settings
from .models import EMAIL, User, VerificationCode
from .notifiers import get_notifier
from .security import hash_secret, verify_secret


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_destination(channel: str, destination: str) -> str:
    if channel == EMAIL and "@" in destination:
        name, domain = destination.split("@", 1)
        head = name[0] if name else ""
        return f"{head}***@{domain}"
    digits = "".join(c for c in destination if c.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


async def issue_code(db: AsyncSession, user: User, *, channel: str, purpose: str) -> VerificationCode:
    code = generate_code()
    destination = user.destination_for(channel)
    vc = VerificationCode(
        user_id=user.id,
        channel=channel,
        purpose=purpose,
        destination=destination,
        code_hash=hash_secret(code),
        dev_code=code if settings.ENV == "dev" else None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.CODE_TTL_MINUTES),
    )
    db.add(vc)
    await db.commit()
    await db.refresh(vc)
    get_notifier().send(channel=channel, destination=destination, code=code, purpose=purpose)
    return vc


async def check_code(db: AsyncSession, vc: VerificationCode, code: str) -> None:
    """Validate a submitted code; raises ContractError on failure, consumes on success."""
    if vc.consumed_at is not None:
        raise errors.code_invalid()
    if datetime.now(timezone.utc) >= vc.expires_at:
        raise errors.code_expired()
    if vc.attempts >= settings.CODE_MAX_ATTEMPTS:
        raise errors.code_max_attempts()

    if not verify_secret(code, vc.code_hash):
        vc.attempts += 1
        await db.commit()
        if vc.attempts >= settings.CODE_MAX_ATTEMPTS:
            raise errors.code_max_attempts()
        raise errors.code_invalid()

    vc.consumed_at = datetime.now(timezone.utc)
    await db.commit()


def challenge_payload(vc: VerificationCode) -> dict:
    return {
        "challenge_id": vc.id,
        "channel": vc.channel,
        "destination": mask_destination(vc.channel, vc.destination),
    }


def user_summary(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email_verified": user.email_verified,
        "phone_verified": user.phone_verified,
    }
