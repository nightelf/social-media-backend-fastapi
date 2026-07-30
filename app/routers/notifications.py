from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..deps import get_current_user, Pagination
from ..models import User, Notification
from ..schemas import NotificationOut, AuthorOut

router = APIRouter(prefix='/api/notifications', tags=['notifications'])

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
                        post_id=n.post_id,
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