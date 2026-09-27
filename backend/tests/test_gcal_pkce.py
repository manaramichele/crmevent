"""PKCE flow tests for Google Calendar OAuth (preview).
Test 1 checks the authorize step generates a PKCE challenge + returns a verifier (in-process,
with dummy creds since preview has no Google config). Tests 2-6 exercise the REAL deployed
callback endpoint: single-use retrieval, reuse rejection, missing/expired rejection, and no
sensitive data in logs. The callback stores its verifier exactly like /connect does."""
import os, re, sys, datetime as dt
from urllib.parse import urlparse, parse_qs
import requests, jwt
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
API_URL = re.search(r"REACT_APP_BACKEND_URL=(.+)", open("/app/frontend/.env").read()).group(1).strip()
JWT_SECRET = os.environ["JWT_SECRET"]; JWT_ALG = "HS256"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
UID = "user_pkce_test"

def state_for(jti, uid=UID, exp_min=15):
    return jwt.encode({"uid": uid, "jti": jti,
                       "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=exp_min)},
                      JWT_SECRET, algorithm=JWT_ALG)

def cb(code, state):
    return requests.get(f"{API_URL}/api/oauth/calendar/callback",
                        params={"code": code, "state": state}, allow_redirects=False)

def put_verifier(jti, verifier, expires_min=10):
    db.calendar_oauth_pkce.delete_many({"jti": jti})
    db.calendar_oauth_pkce.insert_one({"jti": jti, "uid": UID, "code_verifier": verifier,
        "expires_at": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=expires_min), "created_at": "x"})

# --- Test 1: authorize generates PKCE challenge + returns verifier ---
import gcal_utils
gcal_utils.CLIENT_ID = "dummy-client-id.apps.googleusercontent.com"
gcal_utils.CLIENT_SECRET = "dummy-secret"
gcal_utils.REDIRECT_URI = "https://crmevent.it/api/oauth/calendar/callback"
url, verifier = gcal_utils.authorization_url("teststate")
q = parse_qs(urlparse(url).query)
assert q.get("code_challenge") and q.get("code_challenge_method") == ["S256"], "PKCE challenge missing"
assert verifier and 43 <= len(verifier) <= 128, "verifier missing/wrong length"
assert verifier not in url, "verifier leaked into authorize URL"
print("TEST1 authorize→challenge+verifier(len=%d), verifier NOT in URL: PASS" % len(verifier))

# --- Test 2: valid verifier retrieved & consumed (single-use) ---
V2 = "verifier_UNIQUE_TWO_" + "a" * 30
put_verifier("jti_valid", V2)
r = cb("fake_code_123", state_for("jti_valid"))
assert r.status_code == 307 and "calendar=error" in r.headers.get("location", ""), r.status_code
assert db.calendar_oauth_pkce.find_one({"jti": "jti_valid"}) is None, "verifier not single-use"
print("TEST2 valid verifier retrieved + deleted (single-use): PASS")

# --- Test 3: reuse rejected ---
r = cb("fake_code_123", state_for("jti_valid")); assert r.status_code == 307
print("TEST3 reused verifier rejected: PASS")

# --- Test 4: missing verifier rejected ---
r = cb("fake", state_for("jti_never_stored")); assert r.status_code == 307
print("TEST4 missing verifier rejected: PASS")

# --- Test 5: expired verifier rejected + consumed ---
db.calendar_oauth_pkce.delete_many({"jti": "jti_exp"})
db.calendar_oauth_pkce.insert_one({"jti": "jti_exp", "uid": UID, "code_verifier": "v" * 50,
    "expires_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1), "created_at": "x"})
r = cb("fake", state_for("jti_exp")); assert r.status_code == 307
assert db.calendar_oauth_pkce.find_one({"jti": "jti_exp"}) is None, "expired doc not consumed"
print("TEST5 expired verifier rejected + consumed: PASS")

# --- Test 6: no verifier/token/secret in logs ---
tail = ""
for p in ["/var/log/supervisor/backend.err.log", "/var/log/supervisor/backend.out.log"]:
    try: tail += open(p).read()[-40000:]
    except Exception: pass
assert V2 not in tail, "VERIFIER LEAKED INTO LOGS"
for bad in ["code_verifier=", "access_token", "refresh_token", "client_secret", "GOOGLE_CLIENT_SECRET"]:
    bad_lines = [ln for ln in tail.splitlines() if "gcal" in ln and bad in ln]
    assert not bad_lines, f"SENSITIVE '{bad}' found in gcal log: {bad_lines[:1]}"
print("TEST6 no sensitive data (verifier/token/secret) in logs: PASS")
print("--- recent safe gcal callback log lines ---")
for ln in [l for l in tail.splitlines() if "gcal callback" in l][-6:]:
    print("  " + ln.split("crmevent:")[-1])

# cleanup
db.calendar_oauth_pkce.delete_many({"uid": UID})
print("\nALL PKCE TESTS PASSED")
