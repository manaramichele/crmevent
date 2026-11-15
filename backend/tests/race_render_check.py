# Concurrent render race check for promo reels (manual helper)
import os, concurrent.futures as cf, requests, time
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
s = requests.Session(); s.post(f"{B}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
with cf.ThreadPoolExecutor(4) as ex:
    rs = list(ex.map(lambda _: s.post(f"{B}/api/promo-reels/map-15/render").status_code, range(4)))
print("concurrent statuses", rs)
for _ in range(40):
    reel = next(x for x in s.get(f"{B}/api/promo-reels").json()["reels"] if x["slug"] == "map-15")
    if not any(v["status"] in ("queued", "processing") for v in reel["versions"]):
        break
    time.sleep(4)
print([(v["version"], v["status"]) for v in reel["versions"]])
print("restore", s.post(f"{B}/api/promo-reels/map-15/versions/map-15-v1/current").status_code)
