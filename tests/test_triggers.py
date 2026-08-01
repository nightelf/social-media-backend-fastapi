"""Notification triggers: like/comment/follow create notifications; unlike/unfollow remove them.

These test the triggers *through the endpoints* (not by calling notify() directly), so they also
cover the call-site wiring — which is where most of the trigger bugs lived.
"""
from .conftest import auth_header


async def _notifications(client, recipient):
    """The recipient's notifications, newest-first."""
    resp = await client.get("/api/notifications", headers=auth_header(recipient))
    assert resp.status_code == 200
    return resp.json()["results"]


async def test_like_notifies_post_author(client, make_user, make_post):
    author = await make_user()
    actor = await make_user()
    post = await make_post(author)

    resp = await client.post(f"/api/posts/{post.id}/like", headers=auth_header(actor))
    assert resp.status_code == 201

    notifs = await _notifications(client, author)
    assert len(notifs) == 1
    n = notifs[0]
    assert n["type"] == "LIKE"
    assert n["post_id"] == post.id
    assert n["actor"] == {"id": actor.id, "username": actor.username}


async def test_liking_your_own_post_notifies_no_one(client, make_user, make_post):
    """Self-notify guard: acting on your own content creates nothing."""
    author = await make_user()
    post = await make_post(author)

    resp = await client.post(f"/api/posts/{post.id}/like", headers=auth_header(author))
    assert resp.status_code == 201  # you can like your own post...
    assert await _notifications(client, author) == []  # ...but it notifies no one


async def test_unlike_removes_the_notification(client, make_user, make_post):
    author = await make_user()
    actor = await make_user()
    post = await make_post(author)

    await client.post(f"/api/posts/{post.id}/like", headers=auth_header(actor))
    assert len(await _notifications(client, author)) == 1

    await client.delete(f"/api/posts/{post.id}/like", headers=auth_header(actor))
    assert await _notifications(client, author) == []


async def test_each_comment_creates_its_own_notification(client, make_user, make_post):
    """Comments notify per-comment (no dedup) — two comments => two notifications."""
    author = await make_user()
    actor = await make_user()
    post = await make_post(author)

    await client.post(f"/api/posts/{post.id}/comments", headers=auth_header(actor), json={"body": "one"})
    await client.post(f"/api/posts/{post.id}/comments", headers=auth_header(actor), json={"body": "two"})

    notifs = await _notifications(client, author)
    assert [n["type"] for n in notifs] == ["COMMENT", "COMMENT"]
    assert all(n["post_id"] == post.id for n in notifs)


async def test_follow_notifies_then_unfollow_removes(client, make_user):
    followed = await make_user()
    actor = await make_user()

    await client.post(f"/api/users/{followed.username}/follow", headers=auth_header(actor))
    notifs = await _notifications(client, followed)
    assert len(notifs) == 1
    assert notifs[0]["type"] == "FOLLOW"
    assert notifs[0]["post_id"] is None
    assert notifs[0]["actor"]["id"] == actor.id

    await client.delete(f"/api/users/{followed.username}/follow", headers=auth_header(actor))
    assert await _notifications(client, followed) == []
