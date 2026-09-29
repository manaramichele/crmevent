"""Lead Finder scraper — chain: ENDU → sito ufficiale → pagine rilevanti → organizzatore → contatti/social.

Pure, synchronous functions (requests + BeautifulSoup). No paid services, no headless browser.
The server wraps these in `asyncio.to_thread` and handles all DB persistence / dedup.
Design principles honored (per user brief):
- ENDU is the discovery source for events + official links.
- Official/organizer sites are the source of truth for contacts & socials.
- Never invent LinkedIn/Instagram: only links explicitly present on ENDU or the official sites.
- Keep the exact source URL for every datum (email/social/phone).
- Distinguish event site vs organizer site; distinguish event social vs organizer social.
"""
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = "Mozilla/5.0 (compatible; CRMEventLeadFinder/1.0; +https://crmevent.it)"
TIMEOUT = 20
POLITE_DELAY = 0.4  # seconds between requests to the same flow

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# emails/domains that are libraries, CDNs, examples — never real public contacts
EMAIL_BLOCK = ("sentry.", "wixpress.", "example.", "@2x", "@sentry", ".png", ".jpg", ".jpeg",
               ".gif", ".webp", ".svg", "domain.com", "email.com", "yourdomain",
               "godaddy", "u003", "your-email", "gpdp.it", "garanteprivacy",
               "@sentry.io", "cookiebot", "iubenda", "wix.com", "@x.com")
# infra / non-organizer domains we must never follow as an "organizer site"
ORG_SITE_BLOCK = ("google.", "goo.gl", "maps.", "youtube.", "youtu.be", "apple.",
                  "amazon.", "paypal.", "wa.me", "whatsapp.", "t.me", "telegram.",
                  "linktr.ee", "eventbrite.", "endu.net", "microsoft.", "bit.ly")
MAIN_PREFIX = ("info@", "segreteria@", "eventi@", "info.", "contatti@", "contact@",
               "amministrazione@", "presidenza@", "iscrizioni@")

SOCIAL_HOSTS = {
    "instagram": ("instagram.com", "instagr.am"),
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "linkedin": ("linkedin.com", "lnkd.in"),
}
# generic/technical social URLs that must NOT be treated as a profile
SOCIAL_JUNK = ("sharer", "/share", "share.php", "/plugins/", "intent/", "/tr?", "developers.",
               "/policy", "/help", "/login", "/dialog/", "wa.me", "/hashtag/", "/sharer.php")
# ENDU's OWN social accounts (header/footer) — never the event's social
ENDU_OWN_SOCIAL = ("endu_sport", "endu.channel", "endu_net", "@endu_net", "strava.com/clubs/endu",
                   "/enduofficial", "endu.official")

ORG_HINTS = re.compile(
    r"(A\.?S\.?D\.?|S\.?S\.?D\.?|A\.?P\.?S\.?|A\.?S\.?C\.?D\.?|Associazione\s+Sportiva"
    r"|Societ[àa]\s+Sportiva|Polisportiva|Gruppo\s+Sportivo)",
    re.IGNORECASE,
)
# Legal-entity name extractors. Abbreviations are matched case-SENSITIVELY (avoid 'gs'/'as' inside words);
# spelled-out forms case-insensitively. We then capture the following Proper-Case name (1-5 words).
_NAME = r"[«\"'“]?([A-ZÀ-Ù][A-Za-zÀ-ù0-9'&.\-]+(?:\s+(?:[A-ZÀ-Ù0-9][A-Za-zÀ-ù0-9'&.\-]*|di|de|del|della|e)){0,4})"
ORG_ABBR = re.compile(r"\b((?:A\.S\.D\.?|A\.?S\.?D\b|S\.S\.D\.?|S\.?S\.?D\b|A\.P\.S\.?|A\.S\.C\.D\.?|G\.S\.D\.?|G\.S\.?)\.?)\s+" + _NAME)
ORG_SPELLED = re.compile(
    r"\b(Associazione\s+Sportiva(?:\s+Dilettantistica)?|Societ[àa]\s+Sportiva(?:\s+Dilettantistica)?"
    r"|Polisportiva|Gruppo\s+Sportivo)\s+" + _NAME, re.IGNORECASE)
_ORG_BAD = ("iban", "via ", "viale", "piazza", "p.iva", "piva", "partita iva", "c.f", "codice",
            "tel", "email", "@", "cap ", " n.", "numero", "http", "www.", "cookie", "privacy policy")
# internal pages worth visiting on an official site (matched against href + link text)
PAGE_KEYWORDS = ("contatt", "chi-siamo", "chisiamo", "chi_siamo", "about", "organizzaz",
                 "organizzat", "staff", "associazione", "societa", "società", "team",
                 "privacy", "note-legali", "notelegali", "legal", "info", "who-we-are")


def _fetch(url, session=None):
    s = session or requests
    for verify in (True, False):
        try:
            r = s.get(url, headers={"User-Agent": UA, "Accept-Language": "it,en;q=0.8"},
                      timeout=TIMEOUT, allow_redirects=True, verify=verify)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "html" in ct:
                return r.text, r.url
            return None, url
        except requests.exceptions.SSLError:
            continue  # retry once ignoring TLS
        except Exception:
            return None, url
    return None, url


def _host(url):
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _social_kind(url):
    h = _host(url)
    for kind, hosts in SOCIAL_HOSTS.items():
        if any(h == d or h.endswith("." + d) or h == "www." + d for d in hosts):
            return kind
    return None


def _clean_social(url):
    """Normalize a social profile URL; return None if it's a generic/technical link."""
    if not url:
        return None
    low = url.lower()
    if any(j in low for j in SOCIAL_JUNK):
        return None
    url = url.split("?")[0].rstrip("/")
    kind = _social_kind(url)
    # drop paths that are clearly not a profile (e.g. facebook.com/events/123)
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    parts = path.split("/")
    first = parts[0].lower()
    # LinkedIn company/school profiles: normalize to /company/<slug-or-id>
    if kind == "linkedin" and first in ("company", "school") and len(parts) >= 2:
        return f"https://www.linkedin.com/{first}/{parts[1]}"
    if kind == "linkedin" and first == "in" and len(parts) >= 2:
        return f"https://www.linkedin.com/in/{parts[1]}"
    if first in ("p", "reel", "reels", "explore", "events", "groups", "pages", "watch", "posts",
                 "story", "stories", "tv", "photo", "media", "hashtag", "company", "school",
                 "feed", "sharer", "sharing"):
        return None
    return url


def _org_names(text):
    """Extract clean legal-entity names (ASD/SSD/APS/Associazione/Società Sportiva ...)."""
    out = []
    for rx in (ORG_ABBR, ORG_SPELLED):
        for m in rx.finditer(text):
            cand = re.sub(r"\s+", " ", (m.group(1) + " " + m.group(2)).strip(" «\"'“"))
            cand = re.split(r"\.\s|[,;:]", cand)[0].strip()  # drop trailing sentence/noise
            cand = re.sub(r"[.\s]+$", "", cand).strip()
            low = cand.lower()
            if 5 <= len(cand) <= 60 and not any(b in low for b in _ORG_BAD) \
                    and sum(c.isdigit() for c in cand) <= 3:
                out.append(cand)
    return out


# ---------------------------------------------------------------- ENDU parsing
def parse_endu_event(html, base_url):
    """From an ENDU event page, extract the 'Link utili' official site + social page.
    Returns dict: {official_site, social_page, social_kind, instagram, facebook}.
    Only labeled anchors inside 'Link utili' are considered (ENDU's own footer socials are skipped)."""
    out = {"official_site": None, "social_page": None, "social_kind": None,
           "instagram": None, "facebook": None, "labels": {}}
    if not html:
        return out
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        hl = href.lower()
        if "endu.net" in _host(href) or any(x in hl for x in ENDU_OWN_SOCIAL):
            continue
        # the visible label lives in a bold/line-clamp span inside the anchor card
        label = ""
        for sp in a.find_all("span"):
            t = sp.get_text(" ", strip=True)
            if t and 3 <= len(t) <= 60:
                label = t
                break
        if not label:
            continue
        low = label.lower()
        out["labels"][label] = href
        # ONLY labels from the event's "Link utili" carry meaning; ENDU's own footer socials
        # (endu_sport, endu.channel...) have generic labels and are ignored here.
        if "sito ufficiale" in low or (low.startswith("sito") and "ufficiale" in low):
            out["official_site"] = out["official_site"] or href
        elif "social" in low or "instagram" in low or "facebook" in low:
            out["social_page"] = out["social_page"] or href
    # classify the social_page host
    if out["social_page"]:
        out["social_kind"] = _social_kind(out["social_page"])
        if out["social_kind"] == "instagram" and not out["instagram"]:
            out["instagram"] = _clean_social(out["social_page"])
        elif out["social_kind"] == "facebook" and not out["facebook"]:
            out["facebook"] = _clean_social(out["social_page"])
    return out


# ------------------------------------------------------------- official site parsing
def _extract_page(html, page_url):
    """Extract emails/phones/socials/org-name candidates from one HTML page, each with page_url as source."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    res = {"emails": [], "phones": [], "instagram": None, "facebook": None,
           "linkedin": None, "org_candidates": []}

    # mailto / tel links are the most reliable
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("mailto:"):
            e = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.fullmatch(e) and not any(b in e for b in EMAIL_BLOCK):
                res["emails"].append(e)
        elif low.startswith("tel:"):
            ph = re.sub(r"[^\d+]", "", href[4:])
            digits = re.sub(r"\D", "", ph)
            if 8 <= len(digits) <= 13 and not digits.startswith("1234"):
                res["phones"].append(href[4:].strip())
        elif href.startswith("http"):
            k = _social_kind(href)
            if k and not res[k]:
                res[k] = _clean_social(href)

    text = soup.get_text(" ", strip=True)
    for m in EMAIL_RE.findall(text):
        e = m.lower()
        if not any(b in e for b in EMAIL_BLOCK):
            res["emails"].append(e)

    # organizer legal-entity candidates (ASD / SSD / Associazione Sportiva ...)
    res["org_candidates"] = _org_names(text)

    res["emails"] = list(dict.fromkeys(res["emails"]))[:8]
    res["phones"] = list(dict.fromkeys(res["phones"]))[:4]
    res["org_candidates"] = list(dict.fromkeys(res["org_candidates"]))[:6]
    res["_source"] = page_url
    return res


def _pick_internal_pages(html, base_url, limit=5):
    soup = BeautifulSoup(html, "lxml")
    base_host = _host(base_url)
    scored = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if not href.startswith("http") or _host(href) != base_host:
            continue
        href = href.split("#")[0].rstrip("/")
        if not href or href in seen or href.rstrip("/") == base_url.rstrip("/"):
            continue
        blob = (href + " " + a.get_text(" ", strip=True)).lower()
        score = sum(2 if kw in urlparse(href).path.lower() else (1 if kw in blob else 0)
                    for kw in PAGE_KEYWORDS)
        if score > 0:
            seen.add(href)
            scored.append((score, href))
    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:limit]]


def scrape_official_site(start_url, session=None, max_pages=6, follow_org_site=True):
    """Visit an official event/organizer site: homepage + a few relevant internal pages.
    Returns aggregated contacts/socials WITH per-datum source URLs, plus visited pages.
    If the event site links out to an ASD/società site (different domain), follows it once."""
    out = {"start_url": start_url, "org_site": None, "visited": [], "emails": [],
           "email_main": None, "phone": None, "instagram": None, "facebook": None,
           "linkedin": None, "org_name": None, "sources": {}, "error": None}
    session = session or requests.Session()
    home_html, home_url = _fetch(start_url, session)
    if not home_html:
        out["error"] = "sito non raggiungibile"
        return out
    out["start_url"] = home_url
    home_host = _host(home_url)
    pages = [home_url] + _pick_internal_pages(home_html, home_url, limit=max_pages - 1)

    email_src, social_src = {}, {}
    org_candidates = []
    html_by_url = {home_url: home_html}
    for pu in pages:
        html = html_by_url.get(pu)
        if html is None:
            time.sleep(POLITE_DELAY)
            html, real = _fetch(pu, session)
            if not html:
                continue
        out["visited"].append(pu)
        ex = _extract_page(html, pu)
        for e in ex["emails"]:
            email_src.setdefault(e, pu)
        for kind in ("instagram", "facebook", "linkedin"):
            if ex[kind] and kind not in social_src:
                social_src[kind] = (ex[kind], pu)
        if ex["phones"] and not out["phone"]:
            out["phone"] = ex["phones"][0]
            out["sources"]["phone"] = pu
        org_candidates += ex["org_candidates"]

    # Optionally follow an external organizer site linked from the event site (ASD/società on another domain)
    if follow_org_site:
        org_link = None
        soup = BeautifulSoup(home_html, "lxml")
        for a in soup.find_all("a", href=True):
            href = urljoin(home_url, a["href"].strip())
            blob = (href + " " + a.get_text(" ", strip=True)).lower()
            if href.startswith("http") and _host(href) and _host(href) != home_host \
                    and not _social_kind(href) \
                    and not any(b in _host(href) for b in ORG_SITE_BLOCK) \
                    and _org_names(a.get_text(" ", strip=True) or ""):
                org_link = href
                break
        if org_link:
            time.sleep(POLITE_DELAY)
            oh, ou = _fetch(org_link, session)
            if oh:
                out["org_site"] = ou
                out["visited"].append(ou)
                ex = _extract_page(oh, ou)
                for e in ex["emails"]:
                    email_src.setdefault(e, ou)
                for kind in ("instagram", "facebook", "linkedin"):
                    if ex[kind] and kind not in social_src:
                        social_src[kind] = (ex[kind], ou)
                org_candidates += ex["org_candidates"]

    # finalize
    emails = list(email_src.keys())
    out["emails"] = [{"email": e, "source": email_src[e]} for e in emails]
    if emails:
        # rank: emails on the site's own domain first, then role-inboxes, then the rest
        site_dom = _host(home_url)
        def _rank(e):
            dom = e.split("@")[-1]
            same = 0 if (site_dom and (dom == site_dom or dom.endswith("." + site_dom) or site_dom.endswith(dom))) else 1
            role = 0 if any(e.startswith(p) for p in MAIN_PREFIX) else 1
            return (same, role)
        main = sorted(emails, key=_rank)[0]
        out["email_main"] = main
        out["sources"]["email"] = email_src.get(main)
    for kind in ("instagram", "facebook", "linkedin"):
        if kind in social_src:
            out[kind] = social_src[kind][0]
            out["sources"][kind] = social_src[kind][1]
    if org_candidates:
        # prefer a candidate that starts with a legal prefix (ASD/SSD/APS/Associazione/Società);
        # otherwise fall back to the most frequently seen candidate.
        legal = [c for c in org_candidates if re.match(r"^\s*(A\.?S\.?D|S\.?S\.?D|A\.?P\.?S|Associazione|Societ)", c, re.I)]
        pool = legal or org_candidates
        out["org_name"] = max(set(pool), key=pool.count)
    return out


def scan_event(endu_url, session=None):
    """Full chain for one event. Returns a structured result (no DB writes)."""
    session = session or requests.Session()
    res = {"endu_url": endu_url, "endu_ok": False, "official_site": None,
           "social_page": None, "endu_social_kind": None, "endu_instagram": None,
           "endu_facebook": None, "site": None}
    html, real = _fetch(endu_url, session)
    if not html:
        return res
    res["endu_ok"] = True
    links = parse_endu_event(html, real)
    res["official_site"] = links["official_site"]
    res["social_page"] = links["social_page"]
    res["endu_social_kind"] = links["social_kind"]
    res["endu_instagram"] = links["instagram"]
    res["endu_facebook"] = links["facebook"]
    if links["official_site"]:
        time.sleep(POLITE_DELAY)
        res["site"] = scrape_official_site(links["official_site"], session=session)
    return res
