"""Genera la versione 1 dei 7 Reels con lo stesso motore usato dal backend e la pubblica come file statici del frontend."""
import json, os, shutil, sys, time
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
import promo_reels as PR
import promo_reels_render as RR

OUT = "/app/frontend/public/media/reels"
os.makedirs(OUT, exist_ok=True)
man = json.load(open(PR.MANIFEST)) if os.path.exists(PR.MANIFEST) else {}
only = sys.argv[1:]
for r in PR.REELS:
    if only and r["slug"] not in only:
        continue
    t0 = time.time()
    tmp = f"/tmp/reel_{r['slug']}"
    shutil.rmtree(tmp, ignore_errors=True)
    out = RR.render(r["timeline"], PR.ASSETS, tmp, PR.MUSIC)
    s = r["slug"]
    shutil.copy(out["mp4"], f"{OUT}/{s}-v1.mp4")
    shutil.copy(out["mp4_nomusic"], f"{OUT}/{s}-v1-nomusic.mp4")
    shutil.copy(out["cover"], f"{OUT}/{s}-v1-cover.jpg")
    man[s] = {"duration": out["duration"], "size": os.path.getsize(f"{OUT}/{s}-v1.mp4"), "created_at": datetime.now(timezone.utc).isoformat()}
    json.dump(man, open(PR.MANIFEST, "w"), indent=1)
    print(s, out["duration"], man[s]["size"], f"{time.time() - t0:.0f}s", flush=True)
