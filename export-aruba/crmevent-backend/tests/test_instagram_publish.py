"""Unit tests for the Instagram container status-polling flow (fix 'Media ID is not available')."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import instagram_utils as ig  # noqa: E402


async def _nosleep(_):
    return None


def _seq(*states):
    it = iter(states)

    async def _status(_cid, _tok):
        return {"status_code": next(it)}
    return _status


@pytest.mark.anyio
async def test_publishes_only_after_finished(monkeypatch):
    calls = {"publish": 0}

    async def create_media(*a, **k):
        return {"id": "CID1"}

    async def publish_media(uid, cid, tok):
        calls["publish"] += 1
        assert cid == "CID1"  # publishes exactly the creation_id it polled
        return {"id": "MEDIA_REAL_1"}

    monkeypatch.setattr(ig, "create_media", create_media)
    monkeypatch.setattr(ig, "publish_media", publish_media)
    monkeypatch.setattr(ig, "container_status", _seq("IN_PROGRESS", "IN_PROGRESS", "FINISHED"))

    res = await ig.create_and_publish("U", "https://x/y.jpg", "cap", "tok", sleep=_nosleep)
    assert res == {"creation_id": "CID1", "media_id": "MEDIA_REAL_1"}
    assert calls["publish"] == 1  # never published while IN_PROGRESS


@pytest.mark.anyio
async def test_never_publishes_on_timeout(monkeypatch):
    calls = {"publish": 0}

    async def create_media(*a, **k):
        return {"id": "CID2"}

    async def publish_media(*a, **k):
        calls["publish"] += 1
        return {"id": "X"}

    monkeypatch.setattr(ig, "create_media", create_media)
    monkeypatch.setattr(ig, "publish_media", publish_media)
    monkeypatch.setattr(ig, "container_status", lambda *_: _always_in_progress())

    async def _always():
        return {"status_code": "IN_PROGRESS"}
    monkeypatch.setattr(ig, "container_status", lambda *_: _always())

    with pytest.raises(ig.GraphAPIError) as ei:
        await ig.create_and_publish("U", "https://x/y.jpg", "cap", "tok", sleep=_nosleep, max_polls=3)
    assert ei.value.status_code == 504
    assert calls["publish"] == 0  # timeout must NOT publish


@pytest.mark.anyio
async def test_container_error_is_surfaced(monkeypatch):
    async def create_media(*a, **k):
        return {"id": "CID3"}
    monkeypatch.setattr(ig, "create_media", create_media)
    monkeypatch.setattr(ig, "publish_media", lambda *a, **k: None)
    monkeypatch.setattr(ig, "container_status", _seq("IN_PROGRESS", "ERROR"))

    with pytest.raises(ig.GraphAPIError) as ei:
        await ig.create_and_publish("U", "https://x/y.jpg", "cap", "tok", sleep=_nosleep)
    assert ei.value.status_code == 422


@pytest.mark.anyio
async def test_missing_creation_id(monkeypatch):
    async def create_media(*a, **k):
        return {}
    monkeypatch.setattr(ig, "create_media", create_media)
    with pytest.raises(ig.GraphAPIError) as ei:
        await ig.create_and_publish("U", "https://x/y.jpg", "cap", "tok", sleep=_nosleep)
    assert ei.value.status_code == 502


def _always_in_progress():
    pass


@pytest.fixture
def anyio_backend():
    return "asyncio"
