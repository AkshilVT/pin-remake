"""Design JSON → PIL image. Mirrors the page's DOM renderer (same box, fit, crop, text and blend rules)."""

from __future__ import annotations

import math
import re

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from . import core, fonts

BLENDS = ("normal", "multiply", "screen", "overlay", "darken", "lighten", "difference")


def num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def rgb(color, default=(0, 0, 0)):
    try:
        return ImageColor.getrgb(str(color))[:3]
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- per-kind tiles
# Each returns (RGBA tile, offset_x, offset_y): the tile's top-left relative to the layer box's top-left.

_img_cache: dict = {}


def _src(path: str) -> Image.Image | None:
    path = core.expand(path)
    if path not in _img_cache:
        try:
            im = core.open_image(path)
            _img_cache[path] = im.convert("RGBA")
        except Exception as err:  # noqa: BLE001
            print(f"[render] cannot open {path}: {err}")
            _img_cache[path] = None
    return _img_cache[path]


def apply_filter(im: Image.Image, layer: dict) -> Image.Image:
    flt = layer.get("filter") or "none"
    c = float(layer.get("contrast", 1) or 1)
    b = float(layer.get("brightness", 1) or 1)
    if flt == "none" and c == 1 and b == 1:
        return im
    a = np.asarray(im, dtype=np.float32) / 255.0
    rgbv, alpha = a[..., :3], a[..., 3:]
    if flt in ("bw", "sketch"):
        lum = rgbv[..., 0] * 0.2126 + rgbv[..., 1] * 0.7152 + rgbv[..., 2] * 0.0722
        rgbv = np.repeat(lum[..., None], 3, axis=2)
    if c != 1:
        rgbv = (rgbv - 0.5) * c + 0.5
    if b != 1:
        rgbv = rgbv * b
    out = np.concatenate([np.clip(rgbv, 0, 1), alpha], axis=2)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")


def placement(iw, ih, bw, bh, fit, crop):
    """(left, top, width, height) of the image inside the box — CSS object-fit + object-position + scale()."""
    cx = float((crop or {}).get("x", 50))
    cy = float((crop or {}).get("y", 50))
    s = float((crop or {}).get("scale", 1) or 1)
    if fit == "cover":
        k = max(bw / iw, bh / ih)
    elif fit == "contain":
        k = min(bw / iw, bh / ih)
    else:
        k = None
    fw, fh = (bw, bh) if k is None else (iw * k, ih * k)
    ox, oy = (bw - fw) * cx / 100, (bh - fh) * cy / 100
    px, py = bw * cx / 100, bh * cy / 100
    return px + (ox - px) * s, py + (oy - py) * s, fw * s, fh * s


def image_tile(layer, bw, bh):
    im = _src(layer.get("src", ""))
    tile = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    if im is None:
        return tile, 0, 0
    im = apply_filter(im, layer)
    iw, ih = im.size
    left, top, fw, fh = placement(iw, ih, bw, bh, layer.get("fit", "fill"), layer.get("crop"))
    # visible part of the placed image, mapped back to source pixels, then resized once
    vx0, vy0 = max(0.0, left), max(0.0, top)
    vx1, vy1 = min(float(bw), left + fw), min(float(bh), top + fh)
    if vx1 - vx0 >= 1 and vy1 - vy0 >= 1 and fw > 0 and fh > 0:
        sx, sy = iw / fw, ih / fh
        box = ((vx0 - left) * sx, (vy0 - top) * sy, (vx1 - left) * sx, (vy1 - top) * sy)
        dst = (max(1, int(round(vx1 - vx0))), max(1, int(round(vy1 - vy0))))
        part = im.resize(dst, Image.LANCZOS, box=box)
        tile.paste(part, (int(round(vx0)), int(round(vy0))))
    if layer.get("mask"):
        m = _src(layer["mask"])
        if m is not None:
            ma = m.getchannel("A").resize((bw, bh), Image.LANCZOS)
            al = np.asarray(tile.getchannel("A"), dtype=np.float32) * (np.asarray(ma, dtype=np.float32) / 255.0)
            tile.putalpha(Image.fromarray(al.astype(np.uint8), "L"))
    return tile, 0, 0


def rect_tile(layer, bw, bh):
    r, g, b = rgb(layer.get("color", "#000"))
    return Image.new("RGBA", (bw, bh), (r, g, b, 255)), 0, 0


def polygon_tile(layer, bw, bh):
    ss = 3
    pts = layer.get("points") or []
    big = Image.new("L", (bw * ss, bh * ss), 0)
    if len(pts) >= 3:
        ImageDraw.Draw(big).polygon([(p[0] / 100 * bw * ss, p[1] / 100 * bh * ss) for p in pts], fill=255)
    m = big.resize((bw, bh), Image.LANCZOS)
    r, g, b = rgb(layer.get("color", "#000"))
    tile = Image.new("RGBA", (bw, bh), (r, g, b, 0))
    tile.putalpha(m)
    return tile, 0, 0


def _grain(bw, bh, seed=7):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, 1, (bh, bw)).astype(np.float32)
    n = np.asarray(Image.fromarray(np.clip(n * 40 + 128, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.6)), dtype=np.float32)
    v = (n - 128) / 40 * 0.18 + 0.5
    a = np.clip(2 * v - 0.6, 0, 1)
    out = np.zeros((bh, bw, 4), np.uint8)
    out[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def svg_tile(layer, bw, bh):
    if layer.get("preset") == "grain":
        return _grain(bw, bh), 0, 0
    vb = [num(v) for v in re.split(r"[\s,]+", str(layer.get("viewbox") or "0 0 100 100").strip()) if v]
    vx, vy, vw, vh = (vb + [0, 0, 100, 100][len(vb):])[:4] if len(vb) < 4 else vb[:4]
    sx, sy = bw / (vw or 1), bh / (vh or 1)
    ss = 2
    big = Image.new("RGBA", (bw * ss, bh * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    cur = layer.get("color", "#000")
    P = lambda x, y: ((float(x) - vx) * sx * ss, (float(y) - vy) * sy * ss)  # noqa: E731
    for tag, attrs in re.findall(r"<(line|circle|rect|polyline|polygon|ellipse)\b([^>]*)/?>", layer.get("svg", "")):
        a = dict(_ATTR.findall(attrs))
        col = lambda v: None if not v or v == "none" else rgb(cur if v == "currentColor" else v)  # noqa: E731
        stroke, fill = col(a.get("stroke")), col(a.get("fill", "none" if tag in ("line", "polyline") else "#000000"))
        sw = max(1, int(round(float(a.get("stroke-width", 1)) * math.sqrt(sx * sy) * ss)))
        if tag == "line":
            dr.line([P(a.get("x1", 0), a.get("y1", 0)), P(a.get("x2", 0), a.get("y2", 0))], fill=stroke, width=sw)
        elif tag in ("circle", "ellipse"):
            cx, cy = P(a.get("cx", 0), a.get("cy", 0))
            rx = float(a.get("r", a.get("rx", 0))) * sx * ss
            ry = float(a.get("r", a.get("ry", 0))) * sy * ss
            dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=stroke, width=sw if stroke else 0)
        elif tag == "rect":
            x0, y0 = P(a.get("x", 0), a.get("y", 0))
            x1, y1 = P(float(a.get("x", 0)) + float(a.get("width", 0)), float(a.get("y", 0)) + float(a.get("height", 0)))
            dr.rectangle([x0, y0, x1, y1], fill=fill, outline=stroke, width=sw if stroke else 0)
        else:
            nums = [float(v) for v in re.split(r"[\s,]+", a.get("points", "").strip()) if v]
            pts = [P(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            if len(pts) >= 2:
                if tag == "polygon":
                    dr.polygon(pts, fill=fill, outline=stroke)
                else:
                    dr.line(pts, fill=stroke, width=sw)
    return big.resize((bw, bh), Image.LANCZOS), 0, 0


# ---------------------------------------------------------------- text

def _draw_lines(lines, font, px, lh, tracking, align, width, pad, size):
    """Glyph mask (L) of all lines; baseline of line i = (i*lh + lh/2 + 0.35) * px from the box top."""
    mask = Image.new("L", size, 0)
    dr = ImageDraw.Draw(mask)
    tr = tracking / 1000.0 * px
    for i, line in enumerate(lines):
        base = pad + (i * lh + lh * 0.5 + 0.35) * px
        if tr:
            lw = sum(font.getlength(ch) for ch in line) + tr * len(line)
        else:
            lw = font.getlength(line)
        x = pad + (0 if align == "left" or width is None else (width - lw) / 2 if align == "center" else width - lw)
        if tr:
            for ch in line:
                dr.text((x, base), ch, font=font, fill=255, anchor="ls")
                x += font.getlength(ch) + tr
        else:
            dr.text((x, base), line, font=font, fill=255, anchor="ls")
    return mask


def _odd(v):
    v = max(1, int(round(v)))
    return v if v % 2 else v + 1


def _effect(mask: Image.Image, layer, px):
    """(fill mask, inline-line mask or None) for the 'inline' effect: fattened glyph + a light line on the outline."""
    if layer.get("effect") != "inline":
        return mask, None
    fat = mask.filter(ImageFilter.MaxFilter(_odd(0.08 * px)))
    e = _odd(0.025 * px)
    ring = np.asarray(mask.filter(ImageFilter.MaxFilter(e)), np.int16) - np.asarray(mask.filter(ImageFilter.MinFilter(e)), np.int16)
    return fat, Image.fromarray(np.clip(ring, 0, 255).astype(np.uint8), "L")


def _colorize(fill_mask, line_mask, color, line_color):
    r, g, b = rgb(color)
    out = Image.new("RGBA", fill_mask.size, (r, g, b, 0))
    out.putalpha(fill_mask)
    if line_mask is not None:
        lr, lg, lb = rgb(line_color, (255, 255, 255))
        line = Image.new("RGBA", fill_mask.size, (lr, lg, lb, 0))
        line.putalpha(line_mask)
        out = Image.alpha_composite(out, line)
    return out


def text_tile(layer, bw, bh, H):
    lines = str(layer.get("text", "")).split("\n")
    lh = num(layer.get("line_height"), 1) or 1
    tracking = num(layer.get("tracking"), 0)
    fid = layer.get("font", fonts.DEFAULT)
    color, line_color = layer.get("color", "#000"), layer.get("effect_color", "#ffffff")
    if layer.get("fit") == "stretch":
        ref = 200
        font = fonts.load(fid, ref)
        pad = ref
        wid = int(max([font.getlength(ln) for ln in lines] + [1]) + abs(tracking) / 1000 * ref * max(len(ln) for ln in lines) + 2 * pad)
        hei = int((len(lines) * lh + 1) * ref + 2 * pad)
        mask = _draw_lines(lines, font, ref, lh, tracking, "left", None, pad, (wid, hei))
        bb = mask.getbbox()
        if not bb:
            return Image.new("RGBA", (bw, bh), (0, 0, 0, 0)), 0, 0
        fill, line = _effect(mask, layer, ref)
        img = _colorize(fill, line, color, line_color)
        x0, y0, x1, y1 = bb
        sx, sy = bw / max(1, x1 - x0), bh / max(1, y1 - y0)
        p = int(0.06 * ref)
        crop = img.crop((x0 - p, y0 - p, x1 + p, y1 + p))
        out = crop.resize((max(1, int(round(crop.width * sx))), max(1, int(round(crop.height * sy)))), Image.LANCZOS)
        return out, -p * sx, -p * sy
    px = num(layer.get("size"), 4) / 100 * H
    font = fonts.load(fid, px)
    tr = tracking / 1000.0 * px
    widest = max([(sum(font.getlength(ch) for ch in ln) + tr * len(ln)) if tr else font.getlength(ln) for ln in lines] + [1])
    # text may run past the box (the page's SVG overflows visibly): pad by the overflow on both sides
    pad = int(px * 1.2 + max(0.0, widest - bw))
    mask = _draw_lines(lines, font, px, lh, tracking, layer.get("align", "left"), bw, pad, (bw + 2 * pad, bh + 2 * pad + int(px * lh * len(lines))))
    fill, line = _effect(mask, layer, px)
    return _colorize(fill, line, color, line_color), -pad, -pad


# ---------------------------------------------------------------- compositing

def _blend(cb, cs, mode):
    if mode == "multiply":
        return cb * cs
    if mode == "screen":
        return cb + cs - cb * cs
    if mode == "overlay":
        return np.where(cb <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))
    if mode == "darken":
        return np.minimum(cb, cs)
    if mode == "lighten":
        return np.maximum(cb, cs)
    if mode == "difference":
        return np.abs(cb - cs)
    return cs


def composite(canvas: np.ndarray, tile: Image.Image, left: float, top: float, mode: str) -> None:
    H, W = canvas.shape[:2]
    x0, y0 = int(round(left)), int(round(top))
    tw, th = tile.size
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x0 + tw), min(H, y0 + th)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    t = np.asarray(tile, dtype=np.float32)[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] / 255.0
    cs, a = t[..., :3], t[..., 3:4]
    cb = canvas[cy0:cy1, cx0:cx1]
    canvas[cy0:cy1, cx0:cx1] = cb * (1 - a) + _blend(cb, cs, mode) * a


def render(design: dict, scale: float = 1.0) -> Image.Image:
    cv = design.get("canvas", {})
    W = max(1, int(round(float(cv.get("width", 1000)) * scale)))
    H = max(1, int(round(float(cv.get("height", 1250)) * scale)))
    canvas = np.empty((H, W, 3), np.float32)
    canvas[:] = np.array(rgb(cv.get("background", "#ffffff"), (255, 255, 255)), np.float32) / 255.0
    layers = sorted(enumerate(design.get("layers", [])), key=lambda it: (num(it[1].get("z"), it[0]), it[0]))
    for _, L in layers:
        if L.get("visible") is False:
            continue
        bx, by = num(L.get("x")) / 100 * W, num(L.get("y")) / 100 * H
        bwf, bhf = num(L.get("w"), 10) / 100 * W, num(L.get("h"), 10) / 100 * H
        bw, bh = max(1, int(round(bwf))), max(1, int(round(bhf)))
        kind = L.get("kind")
        try:
            if kind == "image":
                tile, ox, oy = image_tile(L, bw, bh)
            elif kind == "text":
                tile, ox, oy = text_tile(L, bw, bh, H)
            elif kind == "rect":
                tile, ox, oy = rect_tile(L, bw, bh)
            elif kind == "polygon":
                tile, ox, oy = polygon_tile(L, bw, bh)
            elif kind == "svg":
                tile, ox, oy = svg_tile(L, bw, bh)
            else:
                continue
        except Exception as err:  # noqa: BLE001 — one broken layer must not sink the export
            print(f"[render] layer {L.get('id')}: {err}")
            continue
        op = num(L.get("opacity"), 1)
        if op < 1:
            a = np.asarray(tile.getchannel("A"), np.float32) * max(0.0, op)
            tile.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
        cx, cy = bx + bwf / 2, by + bhf / 2
        # tile centre relative to the box centre (text tiles carry padding)
        tcx, tcy = ox + tile.width / 2 - bwf / 2, oy + tile.height / 2 - bhf / 2
        rot = num(L.get("rotation"), 0)
        if rot:
            tile = tile.rotate(-rot, expand=True, resample=Image.BICUBIC)
            r = math.radians(rot)
            tcx, tcy = tcx * math.cos(r) - tcy * math.sin(r), tcx * math.sin(r) + tcy * math.cos(r)
        composite(canvas, tile, cx + tcx - tile.width / 2, cy + tcy - tile.height / 2, L.get("blend", "normal"))
    return Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
