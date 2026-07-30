"""Test harness for the FastAPI backend.

Isolation strategy: each test runs inside a single DB transaction that is rolled back at
teardown, so nothing persists and tests never see each other's data. The app's `get_db`
dependency is overridden to yield that same transactional session, so data a test writes is
visible to the endpoint under test (via flush, no commit). Requires the compose Postgres to
be running (the app's DATABASE_URL: localhost:5432 from a venv, db:5432 inside the container).
"""
import uuid
from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Notification, Post, User
from app.security import make_access


@pytest_asyncio.fixture
async def engine():
    # Function-scoped: pytest-asyncio runs each test on its own event loop, and an async
    # engine's connections are bound to the loop they were created on. A session-scoped
    # engine would be reused across loops -> "Event loop is closed".
    eng = create_async_engine(settings.DATABASE_URL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """A session bound to a transaction that is always rolled back — full test isolation."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = async_sessionmaker(bind=conn, expire_on_commit=False)()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db):
    """HTTP client bound to the app, with get_db overridden to the test's transactional session."""
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---- helpers / factories --------------------------------------------------

def auth_header(user: User) -> dict:
    """Authorization header for a user (mints a real access token, exercising get_current_user)."""
    return {"Authorization": f"Bearer {make_access(user.id)}"}


@pytest_asyncio.fixture
async def make_user(db):
    async def _make(username: str | None = None, active: bool = True) -> User:
        uid = uuid.uuid4().hex[:8]
        user = User(
            username=username or f"user_{uid}",
            email=f"{uid}@example.com",
            password_hash="unused-in-tests",
            email_verified=True,
            is_active=active,
        )
        db.add(user)
        await db.flush()
        return user

    return _make


@pytest_asyncio.fixture
async def make_post(db):
    async def _make(author: User, body: str = "hello") -> Post:
        post = Post(author_id=author.id, body=body)
        db.add(post)
        await db.flush()
        return post

    return _make


@pytest_asyncio.fixture
async def make_notification(db):
    async def _make(recipient, actor, type_, post_id=None, read=False) -> Notification:
        n = Notification(
            recipient_id=recipient.id,
            actor_id=actor.id,
            type=type_,
            post_id=post_id,
            read_at=datetime.now(timezone.utc) if read else None,
        )
        db.add(n)
        await db.flush()
        return n

    return _make
