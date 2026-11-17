import sys
sys.path.insert(0, "/app/backend")
import imageio_ffmpeg
import eventmap_render as ER
from PIL import Image

GPX = "/app/backend/tests/fixtures/pisa_run.gpx"
LOGO = "/app/frontend/public/logo-crmevent-header.png"
shots = []
for fmt, title in (("9:16", "Pisa Half Marathon – Edizione Primaverile 2027"), ("16:9", "Pisa Run 2027"), ("1:1", "Trail dei Monti Pisani")):
    job = {"gpx_path": GPX, "style": "streets", "format": fmt, "title": title, "subtitle": "21 km", "date": "12 aprile 2027", "logo_path": LOGO,
           "cache_dir": "/tmp/em_cache", "ffmpeg": imageio_ffmpeg.get_ffmpeg_exe(), "speed": "normal", "show_aid": True, "show_elevation": True,
           "aid_stations": [], "duration": 30, "aid_pause": 3, "aid_pause_auto": False}
    R = ER.Renderer(job)
    for t in (0.01, 0.5, 1.0):
        im = R.frame(t)
        im.thumbnail((360, 360))
        shots.append(im)
W = sum(s.width for s in shots[:3]) + 20
sheet = Image.new("RGB", (W, sum(max(s.height for s in shots[i:i + 3]) for i in (0, 3, 6)) + 20), "white")
y = 0
for i in (0, 3, 6):
    x = 0
    for s in shots[i:i + 3]:
        sheet.paste(s, (x, y))
        x += s.width + 10
    y += max(s.height for s in shots[i:i + 3]) + 10
sheet.save("/app/scripts/promo_video/em_sheet.jpg", quality=80)
print("ok")
