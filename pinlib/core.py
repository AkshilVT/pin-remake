"""Paths, atomic IO, image loading (HEIC included) and photo metadata for Pin Remake."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
from datetime import datetime

from PIL import Image, ImageOps

try:  # HEIC / HEIF — optional; macOS `sips` is the fallback converter
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:  # noqa: BLE001
    HEIF = False

ROOT = os.path.expanduser("~/Fused/pin-remake")
PINS_DIR = os.path.expanduser("~/Desktop/Pintrest-img")
BALI_DIR = os.path.expanduser("~/timepass/bali 07:26")

SUBDIRS = ("sources", "layers", "designs", "originals", "drafts", "exports", "photos", "cutouts", "uploads", "cache")
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp"}
HEIC_EXT = {".heic", ".heif"}

# What each pin is, by mtime order (01 = oldest). Phase 1 builds 01, 03 and 04.
PIN_TITLES = {
    "01": "TOKYO",
    "02": "Temple papercut",
    "03": "Pagoda sketch",
    "04": "Look up, kid",
    "05": "Your Style SHINE",
    "06": "Rule of Thirds",
    "07": "Cruise Memory",
    "08": "City Trace",
    "09": "Eyes / Her",
    "10": "MOTION",
    "11": "Portfolio hero",
}


def d(name: str) -> str:
    return os.path.join(ROOT, name)


def ensure_dirs() -> None:
    for s in SUBDIRS:
        os.makedirs(d(s), exist_ok=True)


def write_atomic(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_json(path: str, obj) -> None:
    write_atomic(path, json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"))


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — missing or unreadable = default
        return default


def save_png(img: Image.Image, path: str) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=6)
    write_atomic(path, buf.getvalue())
    return path


def save_jpg(img: Image.Image, path: str, quality: int = 90) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    write_atomic(path, buf.getvalue())
    return path


def key(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def file_key(path: str, *extra) -> str:
    st = os.stat(path)
    return key(os.path.abspath(path), st.st_mtime_ns, st.st_size, *extra)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:48] or "design"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def expand(path: str) -> str:
    return os.path.abspath(os.path.expanduser((path or "").strip()))


# ---------------------------------------------------------------- image loading

def _sips_jpeg(src: str, max_side: int) -> str:
    """HEIC → JPEG through macOS `sips`, cached by path + mtime + size."""
    out = os.path.join(d("cache"), "heic", file_key(src, max_side) + ".jpg")
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = f"{out}.{os.getpid()}.tmp.jpg"
    cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88"]
    if max_side:
        cmd += ["-Z", str(max_side)]
    subprocess.run(cmd + [src, "--out", tmp], capture_output=True, timeout=40, check=True)
    os.replace(tmp, out)
    return out


def open_image(path: str, max_side: int = 0) -> Image.Image:
    """Oriented RGB / RGBA image; HEIC via pillow-heif or sips; `max_side` downsizes on decode."""
    ext = os.path.splitext(path)[1].lower()
    if ext in HEIC_EXT and not HEIF:
        path = _sips_jpeg(path, max_side or 0)
    with Image.open(path) as src:
        if src.format == "JPEG" and max_side:
            src.draft("RGB", (max_side, max_side))
        im = ImageOps.exif_transpose(src)
        im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if ("A" in im.getbands() or im.mode == "P") else "RGB")
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    return im


def web_copy(path: str, max_side: int = 2400) -> str:
    """A browser-friendly JPEG/PNG copy of any photo (HEIC included) under ~/Fused/pin-remake/photos/."""
    path = expand(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp") and path.startswith(ROOT + os.sep):
        return path
    out_ext = ".png" if ext == ".png" else ".jpg"
    out = os.path.join(d("photos"), f"{slugify(os.path.splitext(os.path.basename(path))[0])}-{file_key(path, max_side)[:8]}{out_ext}")
    if os.path.isfile(out):
        return out
    im = open_image(path, max_side)
    if out_ext == ".png":
        save_png(im, out)
    else:
        save_jpg(im.convert("RGB"), out, 90)
    return out


def thumb(path: str, size: int = 320) -> str:
    path = expand(path)
    out = os.path.join(d("cache"), "thumbs", file_key(path, size) + ".jpg")
    if os.path.isfile(out):
        return out
    im = open_image(path, size)
    im.thumbnail((size, size), Image.LANCZOS)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (235, 233, 228))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    save_jpg(im, out, 82)
    return out


# ---------------------------------------------------------------- photo metadata

PLACES = [
    ("Ubud", -8.5069, 115.2625, 6), ("Tegallalang", -8.4320, 115.2790, 3), ("Tirta Empul", -8.4155, 115.3153, 1.5),
    ("Goa Gajah", -8.5233, 115.2870, 1.0), ("Gianyar", -8.5400, 115.3260, 4), ("Besakih", -8.3742, 115.4517, 2.5),
    ("Seminyak", -8.6913, 115.1682, 2.5), ("Kuta", -8.7180, 115.1690, 2.5), ("Canggu", -8.6478, 115.1385, 3),
    ("Tanah Lot", -8.6212, 115.0868, 2), ("Denpasar", -8.6500, 115.2167, 5), ("Sanur", -8.6900, 115.2620, 3),
    ("Bali Airport", -8.7482, 115.1670, 1.5), ("Jimbaran", -8.7900, 115.1600, 3), ("Nusa Dua", -8.8000, 115.2300, 3.5),
    ("Uluwatu", -8.8291, 115.0849, 3), ("Taman Ayun", -8.5420, 115.1720, 1.5), ("Jatiluwih", -8.3700, 115.1310, 3),
    ("Bedugul", -8.2752, 115.1668, 4), ("Ulun Danu Beratan", -8.2752, 115.1668, 1.0), ("Munduk", -8.2650, 115.0700, 4),
    ("Lovina", -8.1580, 115.0250, 5), ("Kintamani", -8.2500, 115.3300, 4), ("Mount Batur", -8.2420, 115.3750, 5),
    ("Sidemen", -8.4800, 115.4400, 4), ("Tirta Gangga", -8.4120, 115.5870, 2), ("Lempuyang", -8.3910, 115.6310, 2),
    ("Amed", -8.3360, 115.6560, 4), ("Kelingking", -8.7505, 115.4746, 1.5), ("Nusa Penida", -8.7275, 115.5444, 12),
    ("Nusa Lembongan", -8.6800, 115.4500, 2.5), ("Gili Trawangan", -8.3510, 116.0390, 2),
]
TEMPLE_PLACES = {"Tirta Empul", "Goa Gajah", "Besakih", "Tanah Lot", "Uluwatu", "Taman Ayun", "Ulun Danu Beratan",
                 "Lempuyang", "Tirta Gangga"}
BALI_BOX = (-8.95, -8.05, 114.40, 116.10)


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    p = math.pi / 180
    h = math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p) * math.sin((b_lon - a_lon) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def place(lat, lon):
    if lat is None or lon is None:
        return None
    best, bd = None, 1e9
    for name, plat, plon, r in PLACES:
        dist = _km(lat, lon, plat, plon)
        if dist <= r and dist / r < bd:
            best, bd = name, dist / r
    if best:
        return best
    if BALI_BOX[0] <= lat <= BALI_BOX[1] and BALI_BOX[2] <= lon <= BALI_BOX[3]:
        return "Bali"
    return None


def _exif_date(exif):
    raw = None
    try:
        ex = exif.get_ifd(0x8769)
        raw = ex.get(36867) or ex.get(36868)
    except Exception:  # noqa: BLE001
        pass
    raw = raw or exif.get(306)
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", "ignore")
    try:
        dt = datetime.strptime(str(raw).strip()[:19].replace("T", " "), "%Y:%m:%d %H:%M:%S")
        return dt.isoformat(timespec="seconds") if dt.year > 1900 else None
    except Exception:  # noqa: BLE001
        return None


def _exif_gps(exif):
    try:
        g = exif.get_ifd(0x8825)
        la, lo = g.get(2), g.get(4)
        if not la or not lo or len(la) != 3 or len(lo) != 3:
            return None, None
        ref = lambda v: (v.decode() if isinstance(v, bytes) else str(v or "")).strip().upper()  # noqa: E731
        lat = (float(la[0]) + float(la[1]) / 60 + float(la[2]) / 3600) * (-1 if ref(g.get(1)) == "S" else 1)
        lon = (float(lo[0]) + float(lo[1]) / 60 + float(lo[2]) / 3600) * (-1 if ref(g.get(3)) == "W" else 1)
        if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
            return None, None
        return round(lat, 6), round(lon, 6)
    except Exception:  # noqa: BLE001
        return None, None


def _mdls(path: str):
    """Spotlight metadata — date + GPS for files PIL cannot open (HEIC without pillow-heif)."""
    try:
        out = subprocess.run(["mdls", "-name", "kMDItemContentCreationDate", "-name", "kMDItemLatitude",
                              "-name", "kMDItemLongitude", "-name", "kMDItemPixelWidth", "-name", "kMDItemPixelHeight", path],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return {}
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    res = {}
    try:
        res["date"] = datetime.strptime(vals.get("kMDItemContentCreationDate", "")[:19], "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001
        pass
    for k, name in (("lat", "kMDItemLatitude"), ("lon", "kMDItemLongitude")):
        try:
            res[k] = round(float(vals[name]), 6)
        except Exception:  # noqa: BLE001
            pass
    for k, name in (("w", "kMDItemPixelWidth"), ("h", "kMDItemPixelHeight")):
        try:
            res[k] = int(vals[name])
        except Exception:  # noqa: BLE001
            pass
    return res


def photo_meta(path: str) -> dict:
    """{date, date_source, lat, lon, place, w, h} from EXIF (header only), Spotlight, or mtime."""
    st = os.stat(path)
    date, lat, lon, w, h = None, None, None, 0, 0
    try:
        with Image.open(path) as im:
            w, h = im.size
            exif = im.getexif()
        if exif.get(0x0112, 1) in (5, 6, 7, 8):
            w, h = h, w
        date = _exif_date(exif)
        lat, lon = _exif_gps(exif)
    except Exception:  # noqa: BLE001 — HEIC without pillow-heif lands here
        md = _mdls(path)
        date, lat, lon, w, h = md.get("date"), md.get("lat"), md.get("lon"), md.get("w", 0), md.get("h", 0)
    src = "exif" if date else "mtime"
    date = date or datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    return {"date": date, "date_source": src, "lat": lat, "lon": lon, "place": place(lat, lon), "w": w, "h": h,
            "m": st.st_mtime_ns, "s": st.st_size}


def list_images(folder: str) -> list[str]:
    out = []
    for fn in os.listdir(folder):
        if fn.startswith("."):
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext in IMG_EXT or ext in HEIC_EXT:
            p = os.path.join(folder, fn)
            if os.path.isfile(p):
                out.append(p)
    return sorted(out)


def copy_if_changed(src: str, dst: str) -> None:
    try:
        a, b = os.stat(src), os.stat(dst)
        if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
            return
    except OSError:
        pass
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = f"{dst}.{os.getpid()}.tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)
