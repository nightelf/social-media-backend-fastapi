from fastapi import APIRouter, Depends
from sqlalchemy import select, func, update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..deps import get_current_user, Pagination
from ..models import User, Notification, NotificationType
from ..schemas import NotificationOut, AuthorOut, NotificationReadIn, MarkReadOut
from .. import errors

router = APIRouter(prefix='/api/notifications', tags=['notifications'])


async def notify(db: AsyncSession, recipient_id: int, actor_id: int, type_: str, post_id=None):
    exists = (
        await db.execute(
            select(Notification.id).where(
                Notification.post_id == post_id,
                Notification.recipient_id == recipient_id,
                Notification.actor_id == actor_id,
                Notification.type == type_,
            )
        )
    ).first()
    # Comments notify per-comment (no dedup); likes/follows dedup on an existing row. Never self-notify.
    if (exists and type_ == NotificationType.COMMENT.name or not exists) and recipient_id != actor_id:
        notification = Notification(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type_,
            post_id=post_id,
        )
        db.add(notification)


async def unnotify(db: AsyncSession, recipient_id: int, actor_id: int, type_: str, post_id=None):
    """Remove the notification for an undone action (unlike / unfollow). Adds to the session;
    the caller's commit persists it."""
    await db.execute(
        sa_delete(Notification).where(
            Notification.post_id == post_id,
            Notification.recipient_id == recipient_id,
            Notification.actor_id == actor_id,
            Notification.type == type_,
        )
    )


@router.get('')
async def list_notifications(
    pag: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    total = await db.scalar(
        select(func.count(Notification.id)).where(Notification.recipient_id == user.id)
    )

    stmt = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(pag.offset)
        .limit(pag.page_size)
    )

    notifications = (await db.execute(stmt)).scalars().all()
    results = [
        NotificationOut(id=n.id,
                        actor=AuthorOut(id=n.actor.id, username=n.actor.username),
                        type=n.type.name,
                        post_id=n.post_id, seen_at=n.seen_at,
                        read_at=n.read_at, created_at=n.created_at
        )
        .model_dump(mode='json')
        for n in notifications
    ]

    return {
        "results": results,
        "page": pag.page,
        "page_size": pag.page_size,
        "total": total,
        "total_pages": (total + pag.page_size - 1) // pag.page_size,
    }


@router.get('/unseen-count')
async def notifications_unseen_count(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    total = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == user.id,
            Notification.seen_at.is_(None)
        )
    )

    return {
        "count": total
    }

@router.post('/read')
async def notifications_mark_read(
        data: NotificationReadIn,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    # Pydantic checks for presence and int
    id = data.notification_id

    notification = await db.get(Notification, id)
    if not notification:
        raise errors.not_found("notification not found")
    elif notification.recipient_id != user.id:
        raise errors.not_found("Notification not found")

    if notification.read_at is None:
        notification.read_at = func.now()
        await db.commit()
        await db.refresh(notification)

    return MarkReadOut(read_at=notification.read_at)

@router.post('/seen')
async def notifications_mark_seen(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = (
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.seen_at.is_(None))
        .values(seen_at=func.now())
    )
    result = await db.execute(stmt)
    await db.commit()

    return {"count": 0}