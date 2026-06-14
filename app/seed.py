"""Seed identical demo data. Run: python -m app.seed"""
import asyncio

from sqlalchemy import select

from .db import SessionLocal
from .models import Comment, Follow, Like, Post, User
from .security import hash_secret

DEMO = [
    ("ada",   "ada@example.com",   "+15555550101", "Mathematician & first programmer."),
    ("alan",  "alan@example.com",  "+15555550102", "Computing, codebreaking, morphogenesis."),
    ("grace", "grace@example.com", "+15555550103", "Rear admiral. Found the first bug."),
    ("linus", "linus@example.com", "+15555550104", "I just like building kernels."),
]
PASSWORD = "hunter2x!"


async def run():
    async with SessionLocal() as db:
        existing = (await db.execute(select(User).where(User.username == "ada"))).scalar_one_or_none()
        if existing:
            print("Demo data already present; skipping.")
            return

        users = {}
        for username, email, phone, bio in DEMO:
            u = User(
                username=username, email=email, phone=phone, bio=bio,
                password_hash=hash_secret(PASSWORD),
                email_verified=True, phone_verified=True, is_active=True,
            )
            db.add(u)
            users[username] = u
        await db.commit()
        for u in users.values():
            await db.refresh(u)

        posts = [
            Post(author_id=users["ada"].id, body="Hello world — my first post on Sigmagram!"),
            Post(author_id=users["alan"].id, body="Can machines think? Asking for a friend."),
            Post(author_id=users["grace"].id, body="Found a literal moth in the relay today."),
            Post(author_id=users["ada"].id, body="Note G: the engine weaves algebraic patterns."),
            Post(author_id=users["linus"].id, body="Released a small update. Talk is cheap."),
        ]
        db.add_all(posts)
        await db.commit()
        for p in posts:
            await db.refresh(p)

        db.add_all([
            Like(user_id=users["alan"].id, post_id=posts[0].id),
            Like(user_id=users["grace"].id, post_id=posts[0].id),
            Like(user_id=users["ada"].id, post_id=posts[1].id),
            Like(user_id=users["linus"].id, post_id=posts[2].id),
            Comment(post_id=posts[0].id, author_id=users["grace"].id, body="Welcome aboard!"),
            Comment(post_id=posts[1].id, author_id=users["ada"].id, body="They can compute, at least."),
            Comment(post_id=posts[2].id, author_id=users["linus"].id, body="Classic."),
        ])
        follows = [
            ("alan", "ada"), ("grace", "ada"), ("linus", "ada"),
            ("ada", "alan"), ("ada", "grace"),
        ]
        db.add_all([
            Follow(follower_id=users[f].id, followed_id=users[t].id) for f, t in follows
        ])
        await db.commit()
        print(f"Seeded {len(users)} users, {len(posts)} posts. Demo login: ada / {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(run())
