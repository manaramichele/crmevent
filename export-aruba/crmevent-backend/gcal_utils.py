import os
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
BACKEND_URL = os.environ.get("BACKEND_PUBLIC_URL", "")
REDIRECT_URI = f"{BACKEND_URL}/api/oauth/calendar/callback"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def is_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and BACKEND_URL)


def _client_config():
    return {"web": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"}}


def authorization_url(state: str):
    """Return (authorization_url, code_verifier). PKCE code_verifier is generated here and
    must be stored server-side by the caller and passed back to exchange_code()."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state,
                                    include_granted_scopes="true")
    return url, flow.code_verifier


def exchange_code(code: str, code_verifier: str | None = None) -> dict:
    data = {"code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"}
    if code_verifier:
        data["code_verifier"] = code_verifier
    resp = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=30)
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    # Non-sensitive HTTP status attached for diagnostics; callback pops it before persisting.
    data["_http_status"] = resp.status_code
    return data


def userinfo(access_token: str) -> dict:
    return requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"}, timeout=30).json()


def creds_from_tokens(tokens: dict) -> Credentials:
    creds = Credentials(token=tokens.get("access_token"), refresh_token=tokens.get("refresh_token"),
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    return creds


def service_for(tokens: dict):
    return build("calendar", "v3", credentials=creds_from_tokens(tokens), cache_discovery=False)


def list_calendars(tokens: dict):
    svc = service_for(tokens)
    items = svc.calendarList().list().execute().get("items", [])
    return [{"id": c["id"], "summary": c.get("summary", c["id"]), "primary": c.get("primary", False)} for c in items]


def build_event_body(*, summary, description, location, date_start, date_end, time_start=None, time_end=None):
    body = {"summary": summary, "description": description or "", "location": location or ""}
    if time_start:
        s = f"{date_start}T{time_start}:00"
        e = f"{date_end or date_start}T{(time_end or time_start)}:00"
        body["start"] = {"dateTime": s, "timeZone": "Europe/Rome"}
        body["end"] = {"dateTime": e, "timeZone": "Europe/Rome"}
    else:
        end_excl = (datetime.fromisoformat(date_end or date_start) + timedelta(days=1)).date().isoformat()
        body["start"] = {"date": date_start}
        body["end"] = {"date": end_excl}
    return body


def upsert_event(tokens: dict, calendar_id: str, body: dict, google_event_id: str | None):
    svc = service_for(tokens)
    if google_event_id:
        try:
            return svc.events().update(calendarId=calendar_id, eventId=google_event_id, body=body).execute()
        except Exception:
            pass
    return svc.events().insert(calendarId=calendar_id, body=body).execute()
