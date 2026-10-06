import os
import secrets
import mimetypes
import requests

# ---- Emergent object storage (LEGACY: solo lettura di fallback per i file già esistenti) ----
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "crmevent"
_storage_key = None

# ---- Storage locale su filesystem (Aruba, primario) ----
STORAGE_BACKEND = (os.environ.get("STORAGE_BACKEND") or "emergent").strip().lower()
STORAGE_ROOT = (os.environ.get("STORAGE_ROOT") or "/opt/crmevent/storage").rstrip("/")


def _limit_mb(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default)) * 1024 * 1024
    except (TypeError, ValueError):
        return default * 1024 * 1024


MAX_IMAGE = _limit_mb("MAX_UPLOAD_IMAGE_MB", 10)
MAX_PDF = _limit_mb("MAX_UPLOAD_PDF_MB", 20)
MAX_GPX = _limit_mb("MAX_UPLOAD_GPX_MB", 20)
MAX_DATA = _limit_mb("MAX_UPLOAD_DATA_MB", 10)

_EXT = {
    "image": {"jpg", "jpeg", "png", "webp", "gif"},
    "pdf": {"pdf"},
    "gpx": {"gpx", "xml"},
    "data": {"csv", "txt"},
}
_DEFAULT_EXT = {"image": "jpg", "pdf": "pdf", "gpx": "gpx", "data": "txt"}
_LIMIT = {"image": MAX_IMAGE, "pdf": MAX_PDF, "gpx": MAX_GPX, "data": MAX_DATA}
# Solo le immagini ricevono di default un URL pubblico tokenizzato.
PUBLIC_KINDS = {"image"}


def make_token() -> str:
    return secrets.token_urlsafe(32)


def classify_and_validate(filename: str, content_type: str, size: int):
    """Ritorna (kind, ext). Solleva ValueError su tipo non supportato o dimensione eccessiva."""
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    ct = (content_type or "").lower()
    if ext in _EXT["image"] or ct.startswith("image/"):
        kind = "image"
    elif ext in _EXT["pdf"] or ct == "application/pdf":
        kind = "pdf"
    elif ext in _EXT["gpx"] or ct in ("application/gpx+xml", "application/xml", "text/xml"):
        kind = "gpx"
    elif ext in _EXT["data"] or ct in ("text/csv", "text/plain", "application/csv"):
        kind = "data"
    else:
        raise ValueError("unsupported_type")
    if size > _LIMIT[kind]:
        raise ValueError(f"too_large:{kind}")
    if ext not in _EXT[kind]:
        ext = _DEFAULT_EXT[kind]
    return kind, ext


def _safe_local_path(rel_path: str) -> str:
    """Risolve rel_path dentro STORAGE_ROOT impedendo path traversal."""
    root = os.path.realpath(STORAGE_ROOT)
    full = os.path.realpath(os.path.join(root, rel_path))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("path_traversal")
    return full


def save_local(rel_path: str, data: bytes, content_type: str) -> dict:
    full = _safe_local_path(rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)
    return {"path": rel_path, "size": len(data), "backend": "local"}


def read_local(rel_path: str, content_type: str = None):
    full = _safe_local_path(rel_path)
    if not os.path.isfile(full):
        raise FileNotFoundError(rel_path)
    with open(full, "rb") as f:
        data = f.read()
    ct = content_type or mimetypes.guess_type(full)[0] or "application/octet-stream"
    return data, ct


# ---- API unificata ----
def save(rel_path: str, data: bytes, content_type: str) -> dict:
    """Scrive sul backend attivo. Ritorna {path, size, backend}."""
    if STORAGE_BACKEND == "local":
        return save_local(rel_path, data, content_type)
    r = put_object(rel_path, data, content_type)
    r["backend"] = "emergent"
    return r


def read(storage_path: str, backend: str = None, content_type: str = None):
    """Legge dal backend indicato dal documento. Default/None/emergent -> fallback Emergent (legacy)."""
    if backend == "local":
        return read_local(storage_path, content_type)
    return get_object(storage_path)


# ---- Funzioni Emergent legacy (invariate, usate solo per i file preesistenti) ----
def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
