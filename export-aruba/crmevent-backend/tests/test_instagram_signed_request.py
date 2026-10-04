import sys, base64, hmac, hashlib, json
sys.path.insert(0, "/app/backend")
import instagram_utils as ig


def _make(secret, payload):
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), p.encode(), hashlib.sha256).digest()
    s = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{s}.{p}"


ig.APP_SECRET = "test_secret_123"
good = _make("test_secret_123", {"user_id": "17841400000000000", "algorithm": "HMAC-SHA256"})
tampered = _make("wrong_secret", {"user_id": "999"})

assert ig.parse_signed_request(good) == {"user_id": "17841400000000000", "algorithm": "HMAC-SHA256"}
assert ig.parse_signed_request(tampered) is None
assert ig.parse_signed_request("garbage") is None
assert ig.parse_signed_request("") is None
print("signed_request validation OK (valid accepted, tampered/garbage rejected)")
