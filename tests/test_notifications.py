"""Behavior tests for GET /api/notifications.

Focus (in priority order): recipient scoping (the security property that replaced the
{id} path param), auth, response shape, ordering, pagination, empty.
"""
from app.models import NotificationType

from .conftest import auth_header


async def test_only_shows_own_notifications(client, make_user, make_notification):
    """The security-critical test: a user sees ONLY notifications addressed to them."""
    alice = await make_user()
    bob = await make_user()
    # one notification for each recipient
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW)
    await make_notification(recipient=bob, actor=alice, type_=NotificationType.FOLLOW)

    alice_view = (await client.get("/api/notifications", headers=auth_header(alice))).json()
    bob_view = (await client.get("/api/notifications", headers=auth_header(bob))).json()

    assert alice_view["total"] == 1
    assert alice_view["results"][0]["actor"]["username"] == bob.username
    assert bob_view["total"] == 1
    assert bob_view["results"][0]["actor"]["username"] == alice.username


async def test_requires_authentication(client):
    resp = await client.get("/api/notifications")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_response_shape(client, make_user, make_post, make_notification):
    """type serializes as a name (not the int), post_id is nullable, actor is {id, username}."""
    alice = await make_user()
    bob = await make_user()
    post = await make_post(bob)
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.LIKE, post_id=post.id)
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW)  # no post

    results = (await client.get("/api/notifications", headers=auth_header(alice))).json()["results"]
    by_type = {r["type"]: r for r in results}

    assert set(by_type) == {"LIKE", "FOLLOW"}                 # names, not "1"/"3"
    assert by_type["LIKE"]["post_id"] == post.id
    assert by_type["FOLLOW"]["post_id"] is None               # nullable path
    assert by_type["LIKE"]["read_at"] is None                 # unread serializes fine
    assert by_type["LIKE"]["actor"] == {"id": bob.id, "username": bob.username}


async def test_newest_first(client, make_user, make_notification):
    alice = await make_user()
    bob = await make_user()
    for _ in range(3):
        await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW)

    ids = [r["id"] for r in (await client.get("/api/notifications", headers=auth_header(alice))).json()["results"]]
    assert ids == sorted(ids, reverse=True)


async def test_pagination(client, make_user, make_notification):
    alice = await make_user()
    bob = await make_user()
    for _ in range(25):
        await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW)

    page1 = (await client.get("/api/notifications?page=1&page_size=20", headers=auth_header(alice))).json()
    assert page1["total"] == 25
    assert page1["total_pages"] == 2
    assert len(page1["results"]) == 20

    page2 = (await client.get("/api/notifications?page=2&page_size=20", headers=auth_header(alice))).json()
    assert len(page2["results"]) == 5
    # pages don't overlap
    assert not ({r["id"] for r in page1["results"]} & {r["id"] for r in page2["results"]})


async def test_empty_when_no_notifications(client, make_user):
    alice = await make_user()
    data = (await client.get("/api/notifications", headers=auth_header(alice))).json()
    assert data["total"] == 0
    assert data["results"] == []
    assert data["total_pages"] == 0


# ---- GET /api/notifications/unread-count ----------------------------------

async def test_unread_count_excludes_read(client, make_user, make_notification):
    """The count must be unread-only — catches a WHERE clause that drops the read_at filter."""
    alice = await make_user()
    bob = await make_user()
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW, read=False)
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.LIKE, read=False)
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW, read=True)  # excluded

    data = (await client.get("/api/notifications/unread-count", headers=auth_header(alice))).json()
    assert data == {"count": 2}


async def test_unread_count_is_recipient_scoped(client, make_user, make_notification):
    alice = await make_user()
    bob = await make_user()
    await make_notification(recipient=alice, actor=bob, type_=NotificationType.FOLLOW)
    await make_notification(recipient=bob, actor=alice, type_=NotificationType.FOLLOW)  # not alice's

    count = (await client.get("/api/notifications/unread-count", headers=auth_header(alice))).json()["count"]
    assert count == 1


async def test_unread_count_zero_when_none(client, make_user):
    alice = await make_user()
    data = (await client.get("/api/notifications/unread-count", headers=auth_header(alice))).json()
    assert data == {"count": 0}


async def test_unread_count_requires_authentication(client):
    resp = await client.get("/api/notifications/unread-count")
    assert resp.status_code == 401
