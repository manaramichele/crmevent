"""Registratore video: catture reali dell'interfaccia (Playwright) + cursore, evidenziazioni, didascalie e cartelli composti con PIL a 25 fps."""
import io, os, shutil, subprocess
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from common import W, H, clean

FPS = 25
TEAL = (10, 186, 181)
INK = (15, 23, 42)
HERE = Path(__file__).parent
FONT = str(HERE / "fonts" / "Manrope.ttf")
PUB = Path("/app/frontend/public")


def font(size, weight="Bold"):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(weight)
    return f


def ease(t):
    return t * t * (3 - 2 * t)


def cursor_img():
    s = 2.0
    pts = [(4, 2), (19, 11), (12.5, 12.5), (16, 20), (13, 21.5), (9.6, 14.1), (4, 19)]
    im = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    sh = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x * s + 3, y * s + 4) for x, y in pts], fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    ImageDraw.Draw(im).polygon([(x * s, y * s) for x, y in pts], fill=(255, 255, 255, 255), outline=INK + (255,), width=3)
    return im


CURSOR = cursor_img()


class Rec:
    def __init__(self, page, name):
        self.p, self.name = page, name
        self.dir = HERE / "frames" / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.n, self.base, self.cur, self.show_cur = 0, None, [W * 0.62, H * 0.55], False
        self.cap, self.hl, self.ring = None, None, 0.0

    # ---------- composizione ----------
    def _caption_layer(self, im, alpha):
        title, sub = self.cap
        ft, fs = font(40, "ExtraBold"), font(26, "Medium")
        tw = max(ft.getlength(title), fs.getlength(sub) if sub else 0)
        bw, bh = int(tw) + 110, 150 if sub else 104
        x0, y0 = 60, H - 60 - bh
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(lay)
        g.rounded_rectangle((x0 + 6, y0 + 12, x0 + bw + 6, y0 + bh + 12), 26, fill=(0, 0, 0, int(70 * alpha)))
        lay = lay.filter(ImageFilter.GaussianBlur(14))
        g = ImageDraw.Draw(lay)
        g.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 26, fill=INK + (int(240 * alpha),))
        g.rounded_rectangle((x0 + 30, y0 + 30, x0 + 40, y0 + bh - 30), 5, fill=TEAL + (int(255 * alpha),))
        g.text((x0 + 66, y0 + 26), title, font=ft, fill=(255, 255, 255, int(255 * alpha)))
        if sub:
            g.text((x0 + 68, y0 + 86), sub, font=fs, fill=(203, 213, 225, int(255 * alpha)))
        im.alpha_composite(lay)

    def compose(self, base, cap_alpha=1.0):
        im = base.copy()
        if self.hl:
            x, y, w, h = self.hl
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).rounded_rectangle((x - 8, y - 8, x + w + 8, y + h + 8), 12, outline=TEAL + (150,), width=10)
            im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(6)))
            ImageDraw.Draw(im).rounded_rectangle((x - 6, y - 6, x + w + 6, y + h + 6), 10, outline=TEAL + (255,), width=4)
        if self.cap:
            self._caption_layer(im, cap_alpha)
        if self.show_cur:
            cx, cy = self.cur
            if self.ring > 0:
                r = 22 + 26 * (1 - self.ring)
                ImageDraw.Draw(im).ellipse((cx - r, cy - r, cx + r, cy + r), outline=TEAL + (int(255 * self.ring),), width=5)
            im.alpha_composite(CURSOR, (int(cx) - 7, int(cy) - 3))
        return im

    def emit(self, im):
        self.n += 1
        im.convert("RGB").save(self.dir / f"f{self.n:05d}.jpg", quality=90)

    def hold(self, sec):
        im = self.compose(self.base)
        for _ in range(int(sec * FPS)):
            self.emit(im)

    # ---------- catture ----------
    async def shot(self):
        await clean(self.p)
        await self.p.wait_for_timeout(120)
        return Image.open(io.BytesIO(await self.p.screenshot(type="png"))).convert("RGBA")

    async def capture(self, fade=0.4):
        new = await self.shot()
        if self.base is not None and fade:
            k = int(fade * FPS)
            for i in range(1, k + 1):
                self.emit(self.compose(Image.blend(self.base, new, ease(i / k))))
        self.base = new

    async def goto(self, url, wait=1500, fade=0.5):
        await self.p.goto(url, wait_until="networkidle")
        await self.p.wait_for_timeout(wait)
        await self.capture(fade)

    def caption(self, title, sub=None, fade=0.35):
        old = self.cap
        k = int(fade * FPS)
        if old:
            for i in range(k, 0, -1):
                self.emit(self.compose(self.base, i / k))
        self.cap = (title, sub) if title else None
        if self.cap:
            for i in range(1, k + 1):
                self.emit(self.compose(self.base, ease(i / k)))

    async def box(self, loc):
        b = await loc.bounding_box()
        if b is None or b["y"] < 60 or b["y"] + b["height"] > H - 20:
            await loc.scroll_into_view_if_needed()
            await self.p.wait_for_timeout(300)
            await self.capture(0.3)
            b = await loc.bounding_box()
        return b["x"], b["y"], b["width"], b["height"]

    async def point(self, loc, sec=0.75, highlight=True):
        x, y, w, h = await self.box(loc)
        self.show_cur = True
        tx, ty = x + w / 2, y + h / 2
        x0, y0 = self.cur
        k = int(sec * FPS)
        self.hl = (x, y, w, h) if highlight else None
        for i in range(1, k + 1):
            e = ease(i / k)
            self.cur = [x0 + (tx - x0) * e, y0 + (ty - y0) * e]
            self.emit(self.compose(self.base))

    async def click(self, loc, wait=900, fade=0.4, after=0.5, highlight=True):
        await self.point(loc, highlight=highlight)
        for i in range(8):
            self.ring = 1 - i / 8
            self.emit(self.compose(self.base))
        self.ring = 0
        await loc.click()
        await self.p.wait_for_timeout(wait)
        self.hl = None
        await self.capture(fade)
        self.hold(after)

    async def type(self, loc, text, step=3):
        await self.click(loc, wait=200, fade=0.15, after=0.1)
        for i in range(0, len(text), step):
            await loc.type(text[i:i + step])
            await self.capture(0)
            self.hold(0.12)

    async def scroll(self, dy, steps=10, target=None):
        for _ in range(steps):
            if target:
                await target.evaluate(f"(e) => e.scrollBy(0, {dy / steps})")
            else:
                await self.p.mouse.wheel(0, dy / steps)
            await self.p.wait_for_timeout(60)
            await self.capture(0)
            self.hold(0.08)

    # ---------- cartelli ----------
    def card(self, kind, title, sub, sec):
        im = Image.new("RGBA", (W, H), INK + (255,))
        lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gl = ImageDraw.Draw(lines)
        for i in range(0, W + H, 64):
            gl.line([(i, 0), (i - H, H)], fill=(255, 255, 255, 10), width=1)
        im.alpha_composite(lines)
        g = ImageDraw.Draw(im)
        logo = Image.open(PUB / "logo-crmevent-dark.png").convert("RGBA")
        if kind == "intro":
            logo.thumbnail((300, 120))
            im.alpha_composite(logo, (150, 150))
            g.rounded_rectangle((150, 430, 164, 650), 7, fill=TEAL)
            g.text((200, 410), title, font=font(96, "ExtraBold"), fill="white")
            g.text((204, 560), sub, font=font(44, "Medium"), fill=(203, 213, 225))
        else:
            logo.thumbnail((560, 220))
            im.alpha_composite(logo, ((W - logo.width) // 2, 250))
            g.text((W / 2, 610), title, font=font(70, "ExtraBold"), fill="white", anchor="mm")
            g.rounded_rectangle((W / 2 - 250, 720, W / 2 + 250, 810), 45, fill=TEAL)
            g.text((W / 2, 765), "www.crmevent.it", font=font(42, "Bold"), fill=INK, anchor="mm")
            if sub:
                g.text((W / 2, 880), sub, font=font(30, "Medium"), fill=(148, 163, 184), anchor="mm")
        k = int(0.6 * FPS)
        prev = self.compose(self.base) if self.base is not None else Image.new("RGBA", (W, H), INK + (255,))
        for i in range(1, k + 1):
            self.emit(Image.blend(prev, im, ease(i / k)))
        for _ in range(int(sec * FPS)):
            self.emit(im)
        self.card_img = im

    async def leave_card(self, fade=0.6):
        new = await self.shot()
        k = int(fade * FPS)
        for i in range(1, k + 1):
            self.emit(Image.blend(self.card_img, new, ease(i / k)))
        self.base = new
        self.cap, self.hl, self.show_cur = None, None, False


def encode(name, music, poster_sec):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    frames = HERE / "frames" / name
    n = len(list(frames.glob("f*.jpg")))
    dur = n / FPS
    dest = PUB / "media"
    out = dest / f"{name}-demo.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "f%05d.jpg"),
                    "-stream_loop", "-1", "-i", str(dest / "music" / f"{music}.mp3"), "-t", f"{dur:.2f}",
                    "-af", f"volume=0.8,afade=t=in:d=0.8,afade=t=out:st={dur - 2.5:.2f}:d=2.5",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-r", str(FPS),
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)], check=True)
    pf = frames / f"f{int(poster_sec * FPS):05d}.jpg"
    Image.open(pf).convert("RGB").save(dest / f"{name}-demo-poster.jpg", quality=82, optimize=True)
    print(out, os.path.getsize(out), f"{dur:.1f}s")
