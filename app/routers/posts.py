from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .. import errors
from ..db import get_db
from ..deps import Pagination, get_current_user
from ..models import Comment, Follow, Like, Post, User
from ..schemas import AuthorOut, CommentIn, CommentOut, PostIn, PostOut

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _post_out(post: Post, like_count: int, comment_count: int, liked_by_me: bool) -> PostOut:
    return PostOut(
        id=post.id,
        body=post.body,
        author=AuthorOut(id=post.author.id, username=post.author.username),
        like_count=like_count,
        comment_count=comment_count,
        liked_by_me=liked_by_me,
        created_at=post.created_at,
    )


def _annotations(user_id: int):
    like_count = (
        select(func.count(Like.id)).where(Like.post_id == Post.id).scalar_subquery()
    )
    comment_count = (
        select(func.count(Comment.id)).where(Comment.post_id == Post.id).scalar_subquery()
    )
    liked_by_me = (
        select(Like.id).where(Like.post_id == Post.id, Like.user_id == user_id).exists()
    )
    return like_count, comment_count, liked_by_me


async def _fetch_one(db: AsyncSession, post_id: int, user_id: int):
    lc, cc, liked = _annotations(user_id)
    stmt = (
        select(Post, lc.label("lc"), cc.label("cc"), liked.label("liked"))
        .options(selectinload(Post.author))
        .where(Post.id == post_id)
    )
    return (await db.execute(stmt)).first()


@router.get("")
async def list_posts(
    scope: str = Query("all"),
    pag: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lc, cc, liked = _annotations(user.id)
    base = select(Post)
    if scope == "following":
        followed = select(Follow.followed_id).where(Follow.follower_id == user.id)
        base = base.where(Post.author_id.in_(followed))

    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    stmt = (
        select(Post, lc.label("lc"), cc.label("cc"), liked.label("liked"))
        .options(selectinload(Post.author))
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset(pag.offset)
        .limit(pag.page_size)
    )
    if scope == "following":
        followed = select(Follow.followed_id).where(Follow.follower_id == user.id)
        stmt = stmt.where(Post.author_id.in_(followed))

    rows = (await db.execute(stmt)).all()
    results = [_post_out(p, l, c, k).model_dump(mode="json") for p, l, c, k in rows]
    return {
        "results": results,
        "page": pag.page,
        "page_size": pag.page_size,
        "total": total,
        "total_pages": (total + pag.page_size - 1) // pag.page_size,
    }


@router.post("", response_model=PostOut, status_code=201)
async def create_post(
    data: PostIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = Post(author_id=user.id, body=data.body)
    db.add(post)
    await db.commit()
    row = await _fetch_one(db, post.id, user.id)
    p, l, c, k = row
    return _post_out(p, l, c, k)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _fetch_one(db, post_id, user.id)
    if not row:
        raise errors.not_found("No such post.")
    p, l, c, k = row
    return _post_out(p, l, c, k)


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if not post:
        raise errors.not_found("No such post.")
    if post.author_id != user.id:
        raise errors.forbidden("You can only delete your own posts.")
    await db.delete(post)
    await db.commit()
    return Response(status_code=204)


@router.post("/{post_id}/like", status_code=201)
async def like_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Post, post_id):
        raise errors.not_found("No such post.")
    exists = (
        await db.execute(
            select(Like.id).where(Like.post_id == post_id, Like.user_id == user.id)
        )
    ).first()
    if not exists:
        db.add(Like(post_id=post_id, user_id=user.id))
        await db.commit()
    count = await db.scalar(select(func.count(Like.id)).where(Like.post_id == post_id))
    return {"liked_by_me": True, "like_count": count}


@router.delete("/{post_id}/like")
async def unlike_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Post, post_id):
        raise errors.not_found("No such post.")
    await db.execute(
        sa_delete(Like).where(Like.post_id == post_id, Like.user_id == user.id)
    )
    await db.commit()
    count = await db.scalar(select(func.count(Like.id)).where(Like.post_id == post_id))
    return {"liked_by_me": False, "like_count": count}


@router.get("/{post_id}/comments")
async def list_comments(
    post_id: int,
    pag: Pagination = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Post, post_id):
        raise errors.not_found("No such post.")
    total = await db.scalar(
        select(func.count(Comment.id)).where(Comment.post_id == post_id)
    )
    stmt = (
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .offset(pag.offset)
        .limit(pag.page_size)
    )
    comments = (await db.execute(stmt)).scalars().all()
    results = [
        CommentOut(
            id=c.id, body=c.body,
            author=AuthorOut(id=c.author.id, username=c.author.username),
            created_at=c.created_at,
        ).model_dump(mode="json")
        for c in comments
    ]
    return {
        "results": results,
        "page": pag.page,
        "page_size": pag.page_size,
        "total": total,
        "total_pages": (total + pag.page_size - 1) // pag.page_size,
    }


@router.post("/{post_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    post_id: int,
    data: CommentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Post, post_id):
        raise errors.not_found("No such post.")
    comment = Comment(post_id=post_id, author_id=user.id, body=data.body)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)  # populate server-side created_at
    return CommentOut(
        id=comment.id, body=comment.body,
        author=AuthorOut(id=user.id, username=user.username),
        created_at=comment.created_at,
    )
