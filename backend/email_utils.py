import os
import re
import ipaddress
import logging
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

logger = logging.getLogger("crmevent.email")

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "CRMEvent")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")
# Official CRMEvent site logo (public asset served by the deployed frontend). Derived from
# APP_URL so it is always a publicly reachable https URL (preview and production), never a local asset.
_APP_URL = (os.environ.get("APP_URL") or os.environ.get("FRONTEND_URL") or "").rstrip("/")
EMAIL_LOGO_URL = f"{_APP_URL}/logo-crmevent.png" if _APP_URL else "https://crmevent.it/logo-crmevent.png"

# Dedicated provider (Resend, own verified domain crmevent.it). When RESEND_API_KEY
# is set the app sends FROM "CRMEvent <hello@crmevent.it>" (verified domain mailbox).
# Until then it falls back to the managed sender so password-reset/invite emails keep working.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "hello@crmevent.it")
RESEND_BASE_URL = "https://api.resend.com"

# Brevo (Sendinblue) v3 transactional email. Uses the SAME verified sender
# (CRMEvent <hello@crmevent.it>). Sends ONLY via the transactional endpoint
# /v3/smtp/email: it never adds the recipient to any contact list (an invite is
# not a newsletter subscription). Marketing/event lists remain fully separate.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"

# Central switch for the transactional provider. Default "resend" so production
# behaviour is unchanged until the migration is explicitly flipped to "brevo".
# Set EMAIL_PROVIDER=brevo (no code change) to make Brevo primary with Resend fallback.
EMAIL_PROVIDER = (os.environ.get("EMAIL_PROVIDER") or "resend").strip().lower()

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def _send_via_resend(to: str, subject: str, html: str) -> str | None:
    sender = f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{RESEND_BASE_URL}/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": sender, "to": [to], "subject": subject, "html": html},
        )
    resp.raise_for_status()
    return resp.json().get("id")


async def _send_via_brevo(to: str, subject: str, html: str) -> str | None:
    # Transactional only — no contact/list mutation. Sender is the verified CRMEvent mailbox.
    payload = {
        "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDRESS},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            BREVO_EMAIL_URL,
            headers={"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY},
            json=payload,
        )
    resp.raise_for_status()  # error body never contains the api-key
    return (resp.json() or {}).get("messageId")


async def _send_via_managed(to: str, subject: str, html: str) -> str | None:
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                 headers={"X-Email-Key": EMAIL_KEY}, json=payload)
    resp.raise_for_status()
    return resp.json().get("id")


_SENDERS = {"brevo": _send_via_brevo, "resend": _send_via_resend, "managed": _send_via_managed}


def _provider_configured(provider: str) -> bool:
    if provider == "brevo":
        return bool(BREVO_API_KEY and EMAIL_FROM_ADDRESS)
    if provider == "resend":
        return bool(RESEND_API_KEY and EMAIL_FROM_ADDRESS)
    if provider == "managed":
        return bool(EMAIL_KEY)
    return False


def _provider_order() -> list[str]:
    """Ordered providers to try: primary first, then fallbacks (Resend stays available
    as fallback during the migration). Default 'resend' keeps production unchanged."""
    if EMAIL_PROVIDER == "brevo":
        return ["brevo", "resend", "managed"]
    if EMAIL_PROVIDER == "managed":
        return ["managed", "resend"]
    return ["resend", "managed"]


def _mask_email(addr: str) -> str:
    try:
        local, _, dom = (addr or "").partition("@")
        head = local[:2] if len(local) > 2 else local[:1]
        return f"{head}***@{dom}" if dom else "***"
    except Exception:
        return "***"


async def send_email(*, to: str, subject: str, html: str) -> str | None:
    """Send a transactional email through the configured provider with fallback.
    Tracking logs record provider, template (inline), timestamp, outcome and error —
    never the API key, the recipient's full address, the full HTML, or invite tokens."""
    _assert_safe_email(subject, html)
    last_exc = None
    tried = []
    for provider in _provider_order():
        if not _provider_configured(provider):
            continue
        tried.append(provider)
        try:
            message_id = await _SENDERS[provider](to, subject, html)
            logger.info("email_sent provider=%s template=inline to=%s subject=%r message_id=%s status=ok",
                        provider, _mask_email(to), subject, message_id)
            return message_id
        except Exception as exc:  # noqa: BLE001 — try the next provider
            last_exc = exc
            detail = getattr(getattr(exc, "response", None), "status_code", type(exc).__name__)
            logger.warning("email_send_failed provider=%s template=inline to=%s subject=%r status=error error=%s",
                           provider, _mask_email(to), subject, detail)
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Nessun provider email configurato (EMAIL_PROVIDER={EMAIL_PROVIDER}, tentati={tried})")


def _shell(content_html: str) -> str:
    """Shared base layout for CRMEvent internal/transactional emails: white header with the
    centered official logo, dark text, Tiffany accents, client-compatible (Gmail/Outlook/Apple/mobile)."""
    return (
        '<!--[if mso]><style>body,table,td,a{font-family:Arial,Helvetica,sans-serif !important}</style><![endif]-->'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#f4f6f8;margin:0;padding:24px 12px">'
        '<tr><td align="center">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" '
        'style="width:560px;max-width:100%;background:#ffffff;border:1px solid #e6eaef;border-radius:14px">'
        '<tr><td align="center" style="background:#ffffff;padding:30px 32px 10px;border-radius:14px 14px 0 0">'
        f'<img src="{EMAIL_LOGO_URL}" alt="CRMEvent" width="200" '
        'style="display:block;width:200px;max-width:62%;height:auto;border:0;margin:0 auto;outline:none;text-decoration:none" /></td></tr>'
        f'<tr><td style="padding:18px 32px 6px;font-family:Arial,Helvetica,sans-serif">{content_html}</td></tr>'
        '<tr><td style="padding:16px 32px 26px;border-top:1px solid #eef1f5;font-family:Arial,Helvetica,sans-serif">'
        '<p style="color:#9aa4b2;font-size:12px;line-height:1.6;margin:0">Inviato da CRMEvent · Non chiediamo mai password o dati di pagamento via email.</p>'
        '</td></tr></table></td></tr></table>'
    )


def link_email(*, name: str, intro: str, cta_label: str, url: str, footer_note: str) -> str:
    safe_url = escape(url)
    content = (
        f'<p style="color:#0f172a;font-size:16px;font-weight:700;margin:0 0 12px">Ciao {escape(name)},</p>'
        f'<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 22px">{escape(intro)}</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:8px auto 22px">'
        '<tr><td align="center" bgcolor="#81D8D0" style="border-radius:8px">'
        f'<a href="{safe_url}" style="display:inline-block;padding:13px 28px;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:15px;font-weight:700;color:#0f172a;text-decoration:none;border-radius:8px">{escape(cta_label)}</a>'
        '</td></tr></table>'
        '<p style="color:#94a3b8;font-size:12px;line-height:1.6;margin:0 0 4px">Se il pulsante non funziona, copia e incolla questo link nel browser:</p>'
        f'<p style="margin:0 0 18px;word-break:break-all"><span style="color:#59C1B7;font-size:12px">{safe_url}</span></p>'
        f'<p style="color:#94a3b8;font-size:12px;line-height:1.6;margin:0">{escape(footer_note)}</p>'
    )
    return _shell(content)
