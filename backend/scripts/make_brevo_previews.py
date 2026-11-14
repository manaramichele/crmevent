"""Anteprime 16:9 per newsletter Brevo (immagine cliccabile con pulsante Play) dai video demo del sito."""
import os
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MEDIA = os.path.join(ROOT, "frontend", "public", "media")
FONTS = os.path.join(ROOT, "backend", "eventmap_assets", "fonts")
W, H = 1200, 675
TEAL = (10, 186, 181)
ITEMS = [("event-planner", "event-planner-demo.mp4", 20, "EVENT PLANNER", "Progetta il tuo evento"),
         ("event-map", "event-map-demo-gvt.mp4", 15, "EVENT MAP", "Il tuo percorso prende vita")]


def font(size, bold=True):
    return ImageFont.truetype(os.path.join(FONTS, "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"), size)


def frame(video, t):
    out = f"/tmp/brevo_{os.path.basename(video)}.png"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video, "-frames:v", "1", out], check=True)
    im = Image.open(out).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H)).convert("RGBA")


def build(slug, video, t, title, sub):
    im = frame(os.path.join(MEDIA, video), t)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    d.rectangle((0, 0, W, H), fill=(8, 15, 28, 70))
    d.rectangle((0, 0, W, 196), fill=(8, 15, 28, 238))  # fascia titolo opaca: leggibile anche sopra schermate chiare
    d.rectangle((0, 196, W, 202), fill=TEAL + (255,))
    im.alpha_composite(shade)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((56, 52, 56 + 10, 52 + 118), radius=5, fill=TEAL + (255,))
    d.text((88, 48), title, font=font(64), fill=(255, 255, 255, 255))
    d.text((90, 124), sub, font=font(40, False), fill=(226, 232, 240, 255))
    cx, cy, r = W // 2, H // 2 + 40, 78
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - r - 18, cy - r - 18, cx + r + 18, cy + r + 18), fill=(0, 0, 0, 140))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(16)))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TEAL + (255,), outline=(255, 255, 255, 255), width=6)
    d.polygon([(cx - 22, cy - 36), (cx - 22, cy + 36), (cx + 40, cy)], fill=(255, 255, 255, 255))
    d.rounded_rectangle((W // 2 - 190, cy + r + 26, W // 2 + 190, cy + r + 78), radius=26, fill=(8, 15, 28, 215))
    d.text((W // 2, cy + r + 52), "Guarda il video dimostrativo", font=font(26), fill=(255, 255, 255, 255), anchor="mm")
    logo = Image.open(os.path.join(ROOT, "frontend", "public", "logo-crmevent-dark.png")).convert("RGBA")
    logo.thumbnail((230, 70))
    im.alpha_composite(logo, (W - logo.width - 48, (196 - logo.height) // 2))
    os.makedirs(os.path.join(MEDIA, "brevo"), exist_ok=True)
    out = os.path.join(MEDIA, "brevo", f"{slug}-anteprima.jpg")
    im.convert("RGB").save(out, "JPEG", quality=82, optimize=True, progressive=False)
    print(out, os.path.getsize(out))


if __name__ == "__main__":
    for it in ITEMS:
        if len(sys.argv) < 2 or sys.argv[1] == it[0]:
            build(*it)
