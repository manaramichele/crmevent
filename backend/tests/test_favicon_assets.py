"""Favicon/manifest static asset verification (iteration 70).
Verifies CRMEvent new black-calendar favicon served with ?v=6 cache-buster.
"""
import io
import os
import re

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")

# Expected (path, min_size_or_none, expected_square_dim_or_None, mime_prefix)
FAVICON_ASSETS = [
    ("/favicon.ico", "image/", None),               # ICO is multi-size container
    ("/favicon-16.png", "image/png", 16),
    ("/favicon-32.png", "image/png", 32),
    ("/favicon-48.png", "image/png", 48),
    ("/favicon-192.png", "image/png", 192),
    ("/favicon-512.png", "image/png", 512),
    ("/apple-touch-icon.png", "image/png", 180),
    ("/favicon_calendario_nero.png", "image/png", 725),
]


@pytest.mark.parametrize("path,mime,dim", FAVICON_ASSETS)
def test_favicon_asset_served(path, mime, dim):
    url = f"{BASE_URL}{path}?v=6"
    r = requests.get(url, timeout=20)
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    ctype = r.headers.get("content-type", "")
    assert ctype.startswith(mime) or "octet-stream" in ctype, f"bad content-type for {path}: {ctype}"
    assert len(r.content) > 100, f"empty content for {path}"
    if dim is not None:
        img = Image.open(io.BytesIO(r.content))
        w, h = img.size
        assert w == h == dim, f"{path} expected {dim}x{dim}, got {w}x{h}"


def test_favicon_ico_contains_16_32_48():
    url = f"{BASE_URL}/favicon.ico?v=6"
    r = requests.get(url, timeout=20)
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content))
    sizes = set()
    try:
        sizes = set(img.ico.sizes()) if hasattr(img, "ico") else set()
    except Exception:
        sizes = set()
    # Fallback: parse ICONDIR entries
    if not sizes:
        data = r.content
        # ICONDIR: reserved(2) type(2) count(2) ; entries 16 bytes each
        count = int.from_bytes(data[4:6], "little")
        for i in range(count):
            off = 6 + i * 16
            w = data[off] or 256
            h = data[off + 1] or 256
            sizes.add((w, h))
    assert (16, 16) in sizes and (32, 32) in sizes and (48, 48) in sizes, f"ICO sizes={sizes}"


def test_index_html_has_v6_favicon_links_and_no_v5():
    r = requests.get(BASE_URL + "/", timeout=20)
    assert r.status_code == 200
    html = r.text
    # No old v5 references
    assert "?v=5" not in html, "index.html still references ?v=5"
    # Required link tags with ?v=6
    required_patterns = [
        r'rel="icon"[^>]*href="[^"]*favicon\.ico\?v=6"[^>]*sizes="any"',
        r'rel="icon"[^>]*sizes="16x16"[^>]*href="[^"]*favicon-16\.png\?v=6"',
        r'rel="icon"[^>]*sizes="32x32"[^>]*href="[^"]*favicon-32\.png\?v=6"',
        r'rel="icon"[^>]*sizes="48x48"[^>]*href="[^"]*favicon-48\.png\?v=6"',
        r'rel="icon"[^>]*sizes="192x192"[^>]*href="[^"]*favicon-192\.png\?v=6"',
        r'rel="apple-touch-icon"[^>]*sizes="180x180"[^>]*href="[^"]*apple-touch-icon\.png\?v=6"',
    ]
    for pat in required_patterns:
        assert re.search(pat, html), f"missing/incorrect link tag for pattern: {pat}"


def test_manifest_webmanifest_icons_v6():
    r = requests.get(BASE_URL + "/manifest.webmanifest", timeout=20)
    assert r.status_code == 200
    data = r.json()
    srcs = [i["src"] for i in data.get("icons", [])]
    assert any("favicon-192.png?v=6" in s for s in srcs), f"manifest icons: {srcs}"
    assert any("favicon-512.png?v=6" in s for s in srcs), f"manifest icons: {srcs}"
    # Verify the referenced URLs reachable
    for s in srcs:
        iurl = BASE_URL + (s if s.startswith("/") else "/" + s)
        ir = requests.get(iurl, timeout=20)
        assert ir.status_code == 200, f"{iurl} -> {ir.status_code}"


def test_favicon_pixel_palette_matches_calendar_image():
    """New favicon = black calendar on Tiffany (#0ABAB5) background.
    Check 512px version: a corner pixel should be Tiffany-ish, and some central pixels should be dark.
    """
    r = requests.get(BASE_URL + "/favicon-512.png?v=6", timeout=20)
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    w, h = img.size
    # Sample corner (padding area)
    corner = img.getpixel((5, 5))
    cr, cg, cb = corner
    # Allow some tolerance around Tiffany #0ABAB5 / #0CC0C0
    assert cr < 60 and cg > 150 and cb > 150, f"corner not Tiffany-ish: {corner}"
    # Sample many pixels across the image: expect ≥10% dark pixels (black calendar)
    # and ≥20% Tiffany-ish pixels (background).
    step = max(1, w // 40)
    dark = 0
    tiffany = 0
    total = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            r_, g_, b_ = img.getpixel((x, y))
            total += 1
            if r_ < 60 and g_ < 60 and b_ < 60:
                dark += 1
            elif r_ < 60 and g_ > 150 and b_ > 150:
                tiffany += 1
    assert dark / total > 0.1, f"too few dark pixels ({dark}/{total}) - black calendar missing"
    assert tiffany / total > 0.2, f"too few Tiffany pixels ({tiffany}/{total}) - background wrong"
