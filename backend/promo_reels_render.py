"""Montaggio Reels verticali 1080×1920 da progetto riutilizzabile (timeline JSON + schermate reali + clip). Output: MP4 H.264 con e senza musica + copertina JPG."""
import os
import subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import imageio_ffmpeg

W, H, FPS = 1080, 1920, 25
INK, TEAL, MUTED = (15, 23, 42), (10, 186, 181), (203, 213, 225)
CARD_W, CARD_MAX_H = 1000, 1080
FF = imageio_ffmpeg.get_ffmpeg_exe()


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Kit:
    def __init__(self, assets):
        self.assets = assets
        self.fp = os.path.join(assets, "Manrope.ttf")
        self._f = {}
        self.logo = Image.open(os.path.join(assets, "logo.png")).convert("RGBA")
        self.bg = self._bg()
        small = self.logo.copy()
        small.thumbnail((300, 120))
        self.logo_small = small

    def font(self, size, weight="ExtraBold"):
        k = (size, weight)
        if k not in self._f:
            f = ImageFont.truetype(self.fp, size)
            f.set_variation_by_name(weight)
            self._f[k] = f
        return self._f[k]

    def _bg(self):
        im = Image.new("RGBA", (W, H), INK + (255,))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        g.ellipse((-300, -200, 700, 800), fill=TEAL + (60,))
        g.ellipse((500, 1300, 1500, 2300), fill=TEAL + (45,))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
        lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gl = ImageDraw.Draw(lines)
        for i in range(0, W + H, 72):
            gl.line([(i, 0), (i - H, H)], fill=(255, 255, 255, 9), width=1)
        im.alpha_composite(lines)
        return im

    def wrap(self, text, font, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if font.getlength(t) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        return lines + ([cur] if cur else [])


def _card_frame(size):
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 34, fill=255)
    sh = Image.new("RGBA", (w + 120, h + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((60, 75, w + 60, h + 75), 40, fill=(0, 0, 0, 150))
    return mask, sh.filter(ImageFilter.GaussianBlur(28))


class Media:
    """Sorgente di un'inquadratura: schermata (con zoom lento) o clip video."""

    def __init__(self, kit, scene):
        self.scene, self.n = scene, max(1, int(scene["dur"] * FPS))
        if scene.get("clip"):
            p = os.path.join(kit.assets, scene["clip"])
            info = subprocess.run([FF, "-i", p], capture_output=True, text=True).stderr
            import re
            cw, ch = map(int, re.search(r", (\d{3,4})x(\d{3,4})", info).groups())
            self.size = (CARD_W, min(CARD_MAX_H, int(CARD_W * ch / cw)))
            self.proc = subprocess.Popen([FF, "-loglevel", "error", "-ss", str(scene.get("start", 0)), "-i", p, "-t", str(scene["dur"] + 0.5),
                                          "-vf", f"fps={FPS},scale={self.size[0]}:-2,crop={self.size[0]}:{self.size[1]}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                         stdout=subprocess.PIPE)
            self.last = None
        else:
            src = Image.open(os.path.join(kit.assets, scene["asset"])).convert("RGB")
            x, y, w, h = scene.get("crop") or (0, 0, src.width, src.height)
            self.size = (CARD_W, min(CARD_MAX_H, int(CARD_W * h / w)))
            self.big = src.crop((x, y, x + w, y + h)).resize((int(self.size[0] * 1.04), int(self.size[1] * 1.04)), Image.LANCZOS)
            self.proc = None
        self.mask, self.shadow = _card_frame(self.size)

    def frame(self, i):
        if self.proc:
            raw = self.proc.stdout.read(self.size[0] * self.size[1] * 3)
            if len(raw) == self.size[0] * self.size[1] * 3:
                self.last = Image.frombytes("RGB", self.size, raw)
            return self.last or Image.new("RGB", self.size, "white")
        z = 1.04 - 0.035 * ease(i / self.n)
        bw, bh = self.big.size
        cw, ch = int(self.size[0] * z), int(self.size[1] * z)
        x0, y0 = (bw - cw) // 2, (bh - ch) // 2
        return self.big.crop((x0, y0, x0 + cw, y0 + ch)).resize(self.size, Image.BILINEAR)

    def close(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.kill()


def _headline(kit, im, text, t, top=250):
    f = kit.font(72)
    lines = kit.wrap(text, f, 960)
    y = top
    for k, ln in enumerate(lines):
        a = ease((t - 0.12 * k) / 0.45)
        if a <= 0:
            y += 88
            continue
        lay = Image.new("RGBA", (W, 100), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((W / 2, 50), ln, font=f, fill=(255, 255, 255, int(255 * a)), anchor="mm")
        im.alpha_composite(lay, (0, int(y + 30 * (1 - a))))
        y += 88
    bw = int(180 * ease((t - 0.25) / 0.5))
    if bw > 0:
        ImageDraw.Draw(im).rounded_rectangle((W / 2 - bw / 2, y + 22, W / 2 + bw / 2, y + 32), 5, fill=TEAL)
    return y + 80


def _pill(kit, im, text, cy, alpha, size=40, bg=TEAL, fg=INK):
    if alpha <= 0 or not text:
        return
    f = kit.font(size, "Bold")
    tw = f.getlength(text)
    lay = Image.new("RGBA", (W, size * 3), (0, 0, 0, 0))
    g = ImageDraw.Draw(lay)
    g.rounded_rectangle((W / 2 - tw / 2 - 36, size * 0.4, W / 2 + tw / 2 + 36, size * 2.6), size * 1.1, fill=bg + (int(255 * alpha),))
    g.text((W / 2, size * 1.5), text, font=f, fill=fg + (int(255 * alpha),), anchor="mm")
    im.alpha_composite(lay, (0, int(cy - size * 1.5)))


def _section_frame(kit, text, t, media, mframe, label, label_t, prev=None, blend=1.0):
    im = kit.bg.copy()
    im.alpha_composite(kit.logo_small, ((W - kit.logo_small.width) // 2, 110))
    top = _headline(kit, im, text, t)
    cw, chh = media.size
    avail = H - 330 - top
    cy = top + max(0, (avail - chh) // 2) if chh < avail else top
    cx = (W - cw) // 2
    im.alpha_composite(media.shadow, (cx - 60, cy - 60))
    content = mframe if prev is None or blend >= 1 else Image.blend(prev.resize(mframe.size), mframe, blend)
    im.paste(content, (cx, cy), media.mask)
    _pill(kit, im, label, min(H - 210, cy + chh + 90), ease(label_t / 0.35))
    return im


def _hook_frame(kit, text, t, bgimg):
    im = kit.bg.copy()
    if bgimg is not None:
        im.alpha_composite(bgimg)
    im.alpha_composite(kit.logo_small, ((W - kit.logo_small.width) // 2, 110))
    f = kit.font(112)
    lines = kit.wrap(text, f, 940)
    y = H / 2 - len(lines) * 130 / 2
    words_total = sum(len(ln.split()) for ln in lines)
    wi = 0
    for ln in lines:
        ws = ln.split()
        widths = [f.getlength(w + " ") for w in ws]
        x = W / 2 - (sum(widths) - f.getlength(" ")) / 2
        for w, ww in zip(ws, widths):
            a = ease((t - 0.18 * wi) / 0.35)
            if a > 0:
                lay = Image.new("RGBA", (int(ww) + 40, 160), (0, 0, 0, 0))
                col = TEAL if w.endswith("?") or w.endswith("!") else (255, 255, 255)
                ImageDraw.Draw(lay).text((10, 80), w, font=f, fill=col + (int(255 * a),), anchor="lm")
                im.alpha_composite(lay, (int(x - 10), int(y + 20 * (1 - a))))
            x += ww
            wi += 1
        y += 130
    return im


def _outro_frame(kit, text, site, t):
    im = kit.bg.copy()
    a = ease(t / 0.6)
    lg = kit.logo.copy()
    lg.thumbnail((int(640 * (0.9 + 0.1 * a)), 300))
    lay = Image.new("RGBA", lg.size, (0, 0, 0, 0))
    lay.paste(lg, (0, 0))
    lay.putalpha(Image.eval(lg.getchannel("A"), lambda v: int(v * a)))
    im.alpha_composite(lay, ((W - lg.width) // 2, 640 - lg.height // 2))
    b = ease((t - 0.4) / 0.5)
    if b > 0:
        f = kit.font(88)
        for k, ln in enumerate(kit.wrap(text, f, 960)):
            ImageDraw.Draw(im).text((W / 2, 930 + k * 104), ln, font=f, fill=(255, 255, 255, int(255 * b)), anchor="mm")
    _pill(kit, im, site, 1160, ease((t - 0.8) / 0.5), size=54)
    return im


def render(tl, assets, out_dir, music_dir, progress=None):
    kit = Kit(assets)
    os.makedirs(out_dir, exist_ok=True)
    trans = float(tl.get("transition", 0.35))
    sections = tl["sections"]
    first = sections[0]["scenes"][0]
    total = int((tl["hook"]["dur"] + sum(s["dur"] for sec in sections for s in sec["scenes"]) + tl["outro"]["dur"]) * FPS)
    silent = os.path.join(out_dir, "video_nomusic.mp4")
    enc = subprocess.Popen([FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-preset", tl.get("preset", "medium"), "-crf", str(tl.get("crf", 23)), "-pix_fmt", "yuv420p",
                            "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart", silent], stdin=subprocess.PIPE)
    state = {"n": 0, "last": None, "cover": None}
    kblend = max(1, int(trans * FPS))

    def emit(im, seg_i):
        if state["last"] is not None and seg_i < kblend:
            im = Image.blend(state["last"], im, ease((seg_i + 1) / kblend))
        enc.stdin.write(im.convert("RGB").tobytes())
        state["n"] += 1
        if progress and state["n"] % 50 == 0:
            progress(int(95 * state["n"] / total))

    m0 = Media(kit, first)
    hb = m0.frame(m0.n // 2).resize((W, int(W * m0.size[1] / m0.size[0]))).convert("RGBA")
    m0.close()
    hook_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hb = hb.resize((int(hb.width * H / hb.height * 1.0), H)) if hb.height < H else hb
    hook_bg.alpha_composite(hb.filter(ImageFilter.GaussianBlur(26)), ((W - hb.width) // 2, 0))
    hook_bg.putalpha(Image.eval(hook_bg.getchannel("A"), lambda v: int(v * 0.12)))
    n = int(tl["hook"]["dur"] * FPS)
    for i in range(n):
        im = _hook_frame(kit, tl["hook"]["text"], i / FPS, hook_bg)
        emit(im, i if state["last"] is not None else kblend)
    state["last"] = im
    for sec in sections:
        t_sec, seg_i, prev = 0.0, 0, None
        for sc in sec["scenes"]:
            m = Media(kit, sc)
            for i in range(m.n):
                fr = m.frame(i)
                bl = ease((i + 1) / kblend) if prev is not None and i < kblend else 1.0
                im = _section_frame(kit, sec["text"], t_sec, m, fr, sc.get("label"), i / FPS, prev if (prev is not None and prev.size == fr.size) else None, bl)
                if state["cover"] is None and i == m.n - 1:
                    state["cover"] = im.copy()
                emit(im, seg_i)
                t_sec += 1 / FPS
                seg_i += 1
            prev = fr
            m.close()
        state["last"] = im
    n = int(tl["outro"]["dur"] * FPS)
    for i in range(n):
        im = _outro_frame(kit, tl["outro"]["text"], tl["outro"].get("site", "www.crmevent.it"), i / FPS)
        emit(im, i)
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("codifica video non riuscita")
    dur = state["n"] / FPS
    out = {"mp4_nomusic": silent, "duration": round(dur, 2)}
    music = tl.get("music")
    if music:
        mp = os.path.join(music_dir, f"{music}.mp3")
        withm = os.path.join(out_dir, "video.mp4")
        subprocess.run([FF, "-loglevel", "error", "-y", "-i", silent, "-stream_loop", "-1", "-i", mp, "-t", f"{dur:.2f}", "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-af", f"volume=0.85,afade=t=in:d=0.5,afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", withm], check=True)
        out["mp4"] = withm
    else:
        out["mp4"] = silent
    cover = _cover(kit, tl, state["cover"])
    cp = os.path.join(out_dir, "cover.jpg")
    cover.convert("RGB").save(cp, quality=86, optimize=True)
    out["cover"] = cp
    if progress:
        progress(100)
    return out


def _cover(kit, tl, scene_frame):
    im = scene_frame.copy() if scene_frame is not None else kit.bg.copy()
    top = Image.new("RGBA", (W, 760), INK + (255,))
    top.alpha_composite(kit.bg.crop((0, 0, W, 760)))
    im.alpha_composite(top, (0, 0))
    im.alpha_composite(kit.logo_small, ((W - kit.logo_small.width) // 2, 110))
    f = kit.font(84)
    lines = kit.wrap(tl.get("cover_text") or tl["hook"]["text"], f, 960)
    y = 300
    for ln in lines[:4]:
        ImageDraw.Draw(im).text((W / 2, y), ln, font=f, fill="white", anchor="mm")
        y += 100
    g = ImageDraw.Draw(im)
    cx, cy, r = W / 2, 1300, 90
    g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TEAL + (235,))
    g.polygon([(cx - 28, cy - 44), (cx - 28, cy + 44), (cx + 48, cy)], fill=INK)
    _pill(kit, im, "www.crmevent.it", H - 200, 1.0, size=46)
    return im
