"""Routing/fallback tests for the transactional email provider switch (no real send)."""
import os
import sys
import types
import importlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _load(monkeypatch, provider, brevo_key="", resend_key="re_test", email_key="ek_test"):
    monkeypatch.setenv("EMAIL_PROVIDER", provider)
    monkeypatch.setenv("BREVO_API_KEY", brevo_key)
    monkeypatch.setenv("RESEND_API_KEY", resend_key)
    monkeypatch.setenv("EMERGENT_EMAIL_KEY", email_key)
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hello@crmevent.it")
    monkeypatch.setenv("EMAIL_FROM_NAME", "CRMEvent")
    import email_utils
    return importlib.reload(email_utils)


def _stub_senders(eu, calls, failing=()):
    async def mk(name):
        async def _s(to, subject, html):
            calls.append(name)
            if name in failing:
                raise RuntimeError(f"{name} boom")
            return f"{name}-id"
        return _s
    # replace the sender map with async stubs
    async def brevo(to, s, h):
        calls.append("brevo")
        if "brevo" in failing:
            raise RuntimeError("brevo boom")
        return "brevo-id"

    async def resend(to, s, h):
        calls.append("resend")
        if "resend" in failing:
            raise RuntimeError("resend boom")
        return "resend-id"

    async def managed(to, s, h):
        calls.append("managed")
        if "managed" in failing:
            raise RuntimeError("managed boom")
        return "managed-id"

    eu._SENDERS = {"brevo": brevo, "resend": resend, "managed": managed}


def test_order_default_resend(monkeypatch):
    eu = _load(monkeypatch, "resend")
    assert eu._provider_order() == ["resend", "managed"]


def test_order_brevo(monkeypatch):
    eu = _load(monkeypatch, "brevo")
    assert eu._provider_order() == ["brevo", "resend", "managed"]


@pytest.mark.anyio
async def test_brevo_primary_when_configured(monkeypatch):
    eu = _load(monkeypatch, "brevo", brevo_key="xkeysib-test")
    calls = []
    _stub_senders(eu, calls)
    mid = await eu.send_email(to="a@b.com", subject="Test", html="<p>hi</p>")
    assert mid == "brevo-id"
    assert calls == ["brevo"]  # resend NOT called when brevo succeeds


@pytest.mark.anyio
async def test_fallback_to_resend_when_brevo_fails(monkeypatch):
    eu = _load(monkeypatch, "brevo", brevo_key="xkeysib-test")
    calls = []
    _stub_senders(eu, calls, failing=("brevo",))
    mid = await eu.send_email(to="a@b.com", subject="Test", html="<p>hi</p>")
    assert mid == "resend-id"
    assert calls == ["brevo", "resend"]  # fell back to Resend


@pytest.mark.anyio
async def test_brevo_skipped_when_not_configured(monkeypatch):
    # EMAIL_PROVIDER=brevo but no BREVO_API_KEY -> brevo skipped, resend used
    eu = _load(monkeypatch, "brevo", brevo_key="")
    calls = []
    _stub_senders(eu, calls)
    mid = await eu.send_email(to="a@b.com", subject="Test", html="<p>hi</p>")
    assert mid == "resend-id"
    assert calls == ["resend"]


@pytest.mark.anyio
async def test_default_resend_never_uses_brevo(monkeypatch):
    # default provider resend + brevo configured -> brevo must NOT be used
    eu = _load(monkeypatch, "resend", brevo_key="xkeysib-test")
    calls = []
    _stub_senders(eu, calls)
    mid = await eu.send_email(to="a@b.com", subject="Test", html="<p>hi</p>")
    assert mid == "resend-id"
    assert "brevo" not in calls


@pytest.mark.anyio
async def test_raises_when_all_fail(monkeypatch):
    eu = _load(monkeypatch, "brevo", brevo_key="xkeysib-test")
    calls = []
    _stub_senders(eu, calls, failing=("brevo", "resend", "managed"))
    with pytest.raises(Exception):
        await eu.send_email(to="a@b.com", subject="Test", html="<p>hi</p>")
    assert calls == ["brevo", "resend", "managed"]


def test_brevo_payload_shape(monkeypatch):
    """The Brevo sender builds the transactional payload correctly and calls ONLY /smtp/email."""
    eu = _load(monkeypatch, "brevo", brevo_key="xkeysib-test")
    import anyio

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"messageId": "<brevo-msg-1>"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr(eu.httpx, "AsyncClient", FakeClient)

    async def run():
        return await eu._send_via_brevo("dest@example.com", "Oggetto", "<p>ciao</p>")

    mid = anyio.run(run)
    assert mid == "<brevo-msg-1>"
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "xkeysib-test"
    assert captured["json"]["sender"] == {"name": "CRMEvent", "email": "hello@crmevent.it"}
    assert captured["json"]["to"] == [{"email": "dest@example.com"}]
    assert captured["json"]["htmlContent"] == "<p>ciao</p>"
    # transactional only: never touches contacts/lists
    assert "listIds" not in captured["json"]
    assert "contacts" not in captured["url"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
