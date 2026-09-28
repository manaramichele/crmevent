"""CRMEvent Social — creative renderer (Phase C).

Server-side composition of on-brand social creatives (Pillow) + optional AI
background generation (Gemini Nano Banana via Emergent LLM key). No Canva-like
editor: a small reusable template system driven by the post category.
"""
import io
import os
import uuid
import base64
import logging

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("crmevent.creative")

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
IMAGE_PROVIDER = os.environ.get("SOCIAL_IMAGE_PROVIDER", "gemini")
IMAGE_MODEL = os.environ.get("SOCIAL_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

FONT_DIR = "/usr/share/fonts/truetype/liberation/"
TIFFANY = (129, 216, 208)      # #81D8D0 brand accent
DARK = (15, 23, 42)            # slate-900

DIMS = {"4:5": (1080, 1350), "1:1": (1080, 1080), "9:16": (1080, 1920)}
TEMPLATES = ["educational", "problema_soluzione", "funzionalita", "foto_evento", "quote", "commerciale"]
TEMPLATE_TAG = {
    "educational": "EDUCATIONAL", "problema_soluzione": "PROBLEMA → SOLUZIONE",
    "funzionalita": "FUNZIONALITÀ", "foto_evento": "", "quote": "DOMANDA",
    "commerciale": "PROVA CRMEVENT",
}


def _font(size: int, bold: bool = False):
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    for p in (FONT_DIR + name, FONT_DIR + "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hex(s):
    try:
        s = (s or "").lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def _colors(brand_colors):
    primary = None
    for c in (brand_colors or []):
        rgb = _hex(c)
        if rgb:
            primary = rgb
            break
    primary = primary or TIFFANY
    return primary


def _darker(rgb, f=0.55):
    return tuple(max(0, int(c * f)) for c in rgb)


def _cover(img, w, h):
    img = img.convert("RGB")
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _gradient_bg(w, h, top_rgb, bottom_rgb):
    base = Image.new("RGB", (w, h), top_rgb)
    top = Image.new("RGB", (w, h), bottom_rgb)
    mask = Image.new("L", (1, h))
    for y in range(h):
        mask.putpixel((0, y), int(255 * (y / max(1, h - 1))))
    base.paste(top, (0, 0), mask.resize((w, h)))
    return base


def _bottom_scrim(img, frac=0.62, strength=225):
    w, h = img.size
    mask = Image.new("L", (1, h), 0)
    start = 1 - frac
    for y in range(h):
        t = y / max(1, h - 1)
        s = max(0.0, (t - start) / frac)
        mask.putpixel((0, y), int(strength * (s ** 1.25)))
    black = Image.new("RGB", (w, h), (6, 10, 15))
    img.paste(black, (0, 0), mask.resize((w, h)))
    return img


def _wrap(draw, text, font, max_w):
    words = (text or "").split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_block(draw, lines, font, x, y, fill, line_gap=1.15):
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        h = bbox[3] - bbox[1]
        draw.text((x, y), ln, font=font, fill=fill)
        y += int(h * line_gap) + int(font.size * 0.15)
    return y


def _logo_chip(canvas, logo_bytes, x, y):
    if not logo_bytes:
        return
    try:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    except Exception:
        return
    target_h = 84
    ratio = target_h / logo.height
    logo = logo.resize((int(logo.width * ratio), target_h), Image.LANCZOS)
    pad = 22
    chip_w, chip_h = logo.width + pad * 2, target_h + pad * 2
    chip = Image.new("RGBA", (chip_w, chip_h), (255, 255, 255, 235))
    mask = Image.new("L", (chip_w, chip_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, chip_w, chip_h], radius=26, fill=255)
    canvas.paste(chip, (x, y), mask)
    canvas.paste(logo, (x + pad, y + pad), logo)


def _cta_pill(draw, canvas, text, x, y, primary, font):
    if not text:
        return
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 34, 20
    w, h = int(tw + pad_x * 2), int(font.size + pad_y * 2)
    pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([0, 0, w, h], radius=h // 2, fill=primary + (255,))
    canvas.paste(pill, (x, y), pill)
    dd = ImageDraw.Draw(canvas)
    dd.text((x + pad_x, y + pad_y - 2), text, font=font, fill=DARK)
    return h


def render(bg_bytes=None, template="educational", fmt="1:1", hook="", subtitle="",
           cta=None, brand_name="CRMEvent", brand_colors=None, logo_bytes=None):
    """Return PNG bytes of the composed creative."""
    w, h = DIMS.get(fmt, DIMS["1:1"])
    primary = _colors(brand_colors)
    margin = 84

    if template == "funzionalita" and bg_bytes:
        # Panel layout: brand gradient bg + framed screenshot/mockup + top text.
        canvas = _gradient_bg(w, h, _darker(primary, 0.45), _darker(primary, 0.28))
        try:
            shot = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
            card_w = w - margin * 2
            ratio = card_w / shot.width
            card_h = min(int(shot.height * ratio), int(h * 0.38))
            shot = _cover(shot, card_w, card_h)
            card = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
            mask = Image.new("L", (card_w, card_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w, card_h], radius=28, fill=255)
            canvas.paste(shot, (margin, h - margin - card_h), mask)
        except Exception:
            pass
        text_top = margin + 128 + 44  # below the logo chip
        text_color = (255, 255, 255)
    elif bg_bytes:
        canvas = _cover(Image.open(io.BytesIO(bg_bytes)), w, h)
        _bottom_scrim(canvas)
        text_top = None  # bottom-anchored
        text_color = (255, 255, 255)
    else:
        canvas = _gradient_bg(w, h, primary, _darker(primary, 0.5))
        text_top = None
        text_color = (255, 255, 255)

    draw = ImageDraw.Draw(canvas)
    _logo_chip(canvas, logo_bytes, margin, margin)
    draw = ImageDraw.Draw(canvas)

    tag = TEMPLATE_TAG.get(template, "")
    hook_font = _font(84 if fmt != "9:16" else 92, bold=True)
    sub_font = _font(40, bold=False)
    tag_font = _font(30, bold=True)
    cta_font = _font(36, bold=True)

    max_w = w - margin * 2
    hook_lines = _wrap(draw, hook, hook_font, max_w)[:4]
    sub_lines = _wrap(draw, subtitle, sub_font, max_w)[:2]

    # Compute text block height
    def block_h():
        hh = 0
        if tag:
            hh += tag_font.size + 24
        for _ in hook_lines:
            hh += int(hook_font.size * 1.15) + int(hook_font.size * 0.15)
        if sub_lines:
            hh += 18
            for _ in sub_lines:
                hh += int(sub_font.size * 1.2) + int(sub_font.size * 0.15)
        return hh

    total_h = block_h()
    cta_h = (cta_font.size + 40) if cta else 0
    if text_top is None:
        y = h - margin - total_h - (cta_h + 28 if cta else 0)
    else:
        y = text_top

    if tag:
        draw.text((margin, y), tag, font=tag_font, fill=primary)
        y += tag_font.size + 24
    y = _draw_block(draw, hook_lines, hook_font, margin, y, text_color)
    if sub_lines:
        y += 18
        y = _draw_block(draw, sub_lines, sub_font, margin, y, (226, 232, 240))
    if cta:
        fit = cta_font
        limit = max_w - 68
        while draw.textlength(cta, font=fit) > limit and fit.size > 24:
            fit = _font(fit.size - 2, bold=True)
        if draw.textlength(cta, font=fit) > limit:
            while cta and draw.textlength(cta + "…", font=fit) > limit:
                cta = cta[:-1]
            cta = cta.strip() + "…"
        _cta_pill(draw, canvas, cta, margin, y + 20, primary, fit)

    # brand name bottom-right
    bn_font = _font(30, bold=True)
    bn = brand_name or "CRMEvent"
    bw = draw.textlength(bn, font=bn_font)
    draw.text((w - margin - bw, h - margin - 8), bn, font=bn_font, fill=(255, 255, 255))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def to_jpeg(data: bytes) -> bytes:
    """Convert any image bytes to JPEG (Instagram feed requires JPEG)."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=90)
    return out.getvalue()


def creative_bg_prompt(post: dict) -> str:
    base = post.get("image_suggestion") or post.get("topic") or "evento sportivo"
    return (
        "Fotografia realistica e professionale per un post social. Tema: " + base + ". "
        "Contesto: eventi sportivi italiani (running, trail, triathlon, nuoto, ciclismo, tennis). "
        "Luce naturale, colori vivi, composizione pulita con ampio spazio negativo (cielo/parete/asfalto) "
        "nella metà inferiore per inserire testo. "
        "IMPORTANTE: nessun testo, nessuna scritta, nessun numero, nessun logo, nessun watermark nell'immagine."
    )


async def generate_background(prompt: str):
    """Provider-agnostic AI background generation. Returns (png_bytes, meta).

    Only the 'gemini' provider (Nano Banana via the Emergent LLM key, already part of
    the Emergent infrastructure) is wired now — no new dependency/cost. The provider is
    read from SOCIAL_IMAGE_PROVIDER so OpenAI or others can be added later WITHOUT
    changing any caller: the Social module never hard-depends on Gemini.
    """
    provider = IMAGE_PROVIDER
    if provider == "gemini":
        if not LLM_KEY:
            raise RuntimeError("EMERGENT_LLM_KEY mancante")
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex,
                       system_message="Generi immagini fotografiche di sfondo per social di eventi sportivi.")
        chat.with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])
        _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
        if not images:
            raise RuntimeError("Nessuna immagine generata")
        return base64.b64decode(images[0]["data"]), {"provider": "gemini", "model": IMAGE_MODEL, "images": len(images)}
    # Placeholder for future providers (openai, etc.) — intentionally not implemented yet.
    raise NotImplementedError(f"Provider immagini non configurato/supportato: {provider}")
