"""Phase 1 builders: measure the original pins, cut their photo layers, pick Bali photos, write the 6 designs.

Every measurement falls back to the hand-measured spec value when detection fails, so a build always
produces a usable design; the compare view shows how close it got.
"""

from __future__ import annotations

import copy
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import core

INK = (28, 27, 25)
SLUGS = {"01": "01-tokyo", "03": "03-pagoda-sketch", "04": "04-look-up-kid"}
NAMES = {"01": "TOKYO", "03": "Pagoda sketch", "04": "Look up, kid"}


# ---------------------------------------------------------------- small helpers

def arr(im: Image.Image) -> np.ndarray:
    return np.asarray(im.convert("RGB"), dtype=np.int16)


def hexc(c) -> str:
    c = [int(round(float(v))) for v in list(c)[:3]]
    return "#%02x%02x%02x" % tuple(max(0, min(255, v)) for v in c)


def median_color(a: np.ndarray, mask: np.ndarray | None = None, default=(128, 128, 128)):
    px = a.reshape(-1, 3) if mask is None else a[mask]
    if px.size == 0:
        return default
    return tuple(np.median(px, axis=0))


def r2(v) -> float:
    return round(float(v), 3)


def poly_mask(W: int, H: int, pts_pct, ss: int = 3) -> np.ndarray:
    """Anti-aliased polygon mask (0..1) for points in % of the canvas."""
    big = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(big).polygon([(x / 100 * W * ss, y / 100 * H * ss) for x, y in pts_pct], fill=255)
    return np.asarray(big.resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0


def bbox(mask: np.ndarray, thresh: float = 0.02, min_count: int = 1):
    rows = np.where((mask > thresh).sum(1) >= min_count)[0]
    cols = np.where((mask > thresh).sum(0) >= min_count)[0]
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def runs(flags: np.ndarray, min_len: int = 1):
    """[(start, end_exclusive)] of True runs."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def save_cut(pin: str, name: str, rgb_img: Image.Image, alpha: np.ndarray, box=None, color=None):
    """Crop to the alpha bbox, write <name>.png (RGBA) + <name>-mask.png; return (src, mask, box%)."""
    W, H = rgb_img.size
    bb = box or bbox(alpha, 0.03) or (0, 0, W, H)
    x0, y0, x1, y1 = bb
    if color is not None:
        base = Image.new("RGB", (W, H), color)
    else:
        base = rgb_img.convert("RGB")
    a8 = Image.fromarray(np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8), "L")
    rgba = base.copy()
    rgba.putalpha(a8)
    folder = os.path.join(core.d("layers"), pin)
    src = core.save_png(rgba.crop(bb), os.path.join(folder, f"{name}.png"))
    m = Image.new("RGBA", (x1 - x0, y1 - y0), (255, 255, 255, 0))
    m.putalpha(a8.crop(bb))
    mask = core.save_png(m, os.path.join(folder, f"{name}-mask.png"))
    return src, mask, (x0 / W * 100, y0 / H * 100, (x1 - x0) / W * 100, (y1 - y0) / H * 100)


def layer(lid, name, kind, x, y, w, h, z, **kw):
    base = {"id": lid, "name": name, "kind": kind, "visible": True, "locked": False,
            "x": r2(x), "y": r2(y), "w": r2(w), "h": r2(h), "rotation": 0, "z": z, "opacity": 1, "blend": "normal"}
    if kind == "image":
        base.update({"src": "", "src_orig": "", "src_raw": "", "mask": "", "fit": "fill",
                     "crop": {"x": 50, "y": 50, "scale": 1}, "filter": "none", "contrast": 1, "brightness": 1, "swap": "mask"})
    elif kind == "text":
        base.update({"text": "", "font": "hn-medium", "size": 4, "weight": 400, "color": "#000000", "tracking": 0,
                     "line_height": 1, "align": "left", "fit": "none", "effect": "none", "effect_color": "#ffffff"})
    else:
        base["color"] = "#000000"
    base.update(kw)
    if kind == "image":
        base["src_orig"] = base["src_orig"] or base["src"]
        base["src_raw"] = base["src_raw"] or base["src"]
        base["mask_orig"] = base.get("mask_orig") or base["mask"]
    if lid in ("paper", "grain", "cream", "red"):
        base["locked"] = True  # full-canvas backgrounds: click-through by default, unlock from the layer list
    return base


def aspect(W: int, H: int) -> str:
    best, err = f"{W}:{H}", 1e9
    for a, b in ((4, 5), (2, 3), (3, 4), (9, 16), (1, 1), (5, 7)):
        e = abs(W / H - a / b)
        if e < err:
            best, err = f"{a}:{b}", e
    return best if err < 0.03 else f"{W}:{H}"


def design(pin, slug, name, src, orig, W, H, bg, layers, variant_of=None, notes=""):
    t = core.now_iso()
    return {"version": 1, "slug": slug, "name": name, "pin": pin, "variant_of": variant_of,
            "source": src, "source_original": orig,
            "canvas": {"width": W, "height": H, "aspect": aspect(W, H), "background": bg},
            "layers": layers, "notes": notes, "created": t, "updated": t}


def write_design(d: dict, force: bool) -> None:
    core.write_json(os.path.join(core.d("originals"), d["slug"] + ".json"), d)
    path = os.path.join(core.d("designs"), d["slug"] + ".json")
    if force or not os.path.isfile(path):
        core.write_json(path, d)
        try:
            os.remove(os.path.join(core.d("drafts"), d["slug"] + ".json"))
        except OSError:
            pass


# ---------------------------------------------------------------- identify pins

def pin_scores(path: str) -> dict:
    im = core.open_image(path, 400)
    a = arr(im)
    H, W = a.shape[:2]
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    red = (R > 150) & (G < 90) & (B < 90)
    yellow = (R > 190) & (G > 150) & (B < 110) & (R - B > 110)
    orange = (R > 200) & (G > 90) & (G < 190) & (B < 110) & (R - B > 110)
    return {
        "tokyo": float(red[H // 2:].mean()),
        "yellow": float(yellow.mean()),
        "lookup": float(orange[int(H * .6):, W // 2:].mean()) + float(((np.abs(a - np.array([232, 232, 230])).max(2)) < 16).mean()) * 0.2,
    }


def assign_roles(sources: list[dict]) -> dict:
    """{"01": n, "03": n, "04": n} — mtime numbering, corrected when a colour signature says otherwise."""
    scores = {s["n"]: s.get("scores", {}) for s in sources}
    roles = {}
    for pin, feat, thresh in (("01", "tokyo", 0.2), ("03", "yellow", 0.03), ("04", "lookup", 0.004)):
        if pin in scores and scores[pin].get(feat, 0) >= thresh:
            roles[pin] = pin
            continue
        cand = sorted(scores, key=lambda n: -scores[n].get(feat, 0))
        cand = [n for n in cand if n not in roles.values()]
        roles[pin] = cand[0] if cand and scores[cand[0]].get(feat, 0) >= thresh else (pin if pin in scores else None)
    return roles


# ---------------------------------------------------------------- pin 01 · TOKYO

def build_tokyo(src: str, orig: str, force: bool) -> dict:
    im = core.open_image(src).convert("RGB")
    W, H = im.size
    a = arr(im)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    sat = mx - mn
    red = (R > 150) & (G < 95) & (B < 95) & (R - G > 80)

    cream = median_color(a[int(H * .01):int(H * .08), int(W * .01):int(W * .2)])
    x0s, x1s = max(1, int(W * .003)), max(int(W * .02), int(W * .003) + 3)
    frac = red[:, x0s:x1s].mean(1)
    rows = [r for r in np.where(frac > .6)[0] if r > H * .25]
    split = int(rows[0]) if rows else int(H * .475)
    redc = median_color(a, red & (np.arange(H)[:, None] > split) & (np.arange(W)[None, :] < W * .15))

    # TOKYO: the visible red letters above the split
    letters = red.copy()
    letters[split - 1:] = False
    bb = bbox(letters.astype(np.float32), 0.5, 3)
    if bb:
        tx0, ty0, tx1, _ = bb
    else:
        tx0, ty0, tx1 = int(W * .027), int(H * .185), int(W * .969)
    ty1 = split + 0.06 * (split - ty0)

    # labels: dark caps on cream
    dark = (mx < 110) & (sat < 45)
    def label_box(xa, xb, fallback):
        m = np.zeros((H, W), np.float32)
        m[int(H * .05):int(H * .18), int(W * xa):int(W * xb)] = dark[int(H * .05):int(H * .18), int(W * xa):int(W * xb)]
        return bbox(m, 0.5, 2) or fallback
    asa = label_box(0, .40, (int(W * .041), int(H * .116), int(W * .279), int(H * .149)))
    jap = label_box(.58, .87, (int(W * .724), int(H * .116), int(W * .882), int(H * .149)))
    lab_mask = np.zeros((H, W), bool)
    for x0, y0, x1, y1 in (asa, jap):
        lab_mask[max(0, y0 - 3):y1 + 3, max(0, x0 - 3):x1 + 3] = True
    labc = median_color(a, dark & lab_mask & (mx < 85), (40, 38, 36))

    # grayscale photo pixels: low saturation and not cream
    cream_d = np.abs(a - np.array(cream)).max(2)
    below = np.arange(H)[:, None] >= split          # under the split only red competes: any grey pixel is photo
    core_m = ((sat < 48) & (below | (cream_d > 26)) & ~lab_mask).astype(np.uint8) * 255
    core_i = Image.fromarray(core_m, "L").filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MaxFilter(3))
    photo = np.asarray(core_i, np.float32) / 255.0
    photo[lab_mask] = 0

    regions = {
        "pagoda": [(44, 3), (56, 3), (56, 24), (79, 25), (85, 45), (85, 80), (15, 80), (15, 45), (20, 25), (44, 24)],
        "roofs": [(0, 61), (30, 61), (30, 80), (58, 80), (58, 70), (85, 70), (85, 61), (100, 61), (100, 100), (0, 100)],
        "eaves": [(85, 6), (100, 6), (100, 61), (85, 61)],
    }
    cuts = {}
    for name, pts in regions.items():
        alpha = photo * poly_mask(W, H, pts)
        alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5)), np.float32) / 255.0
        cuts[name] = save_cut("01", name, im, alpha)

    sp = split / H * 100
    lay = [
        layer("cream", "Cream block", "rect", 0, 0, 100, sp, 0, color=hexc(cream)),
        layer("red", "Red block", "rect", 0, sp, 100, 100 - sp, 1, color=hexc(redc)),
        layer("tokyo", "TOKYO", "text", tx0 / W * 100, ty0 / H * 100, (tx1 - tx0) / W * 100, (ty1 - ty0) / H * 100, 2,
              text="TOKYO", font="hn-cond-black", weight=900, color=hexc(redc), fit="stretch", size=30),
    ]
    for z, (lid, nm, swap) in enumerate((("pagoda", "Pagoda cut-out", "cutout"), ("eaves", "Eaves (right edge)", "mask"),
                                          ("roofs", "Temple roofs", "mask")), start=3):
        s, m, (x, y, w, h) = cuts[lid]
        lay.append(layer(lid, nm, "image", x, y, w, h, z, src=s, mask=m, filter="bw", swap=swap))
    for z, (lid, txt, bx) in enumerate((("asakusa", "ASAKUSA", asa), ("japan", "JAPAN", jap)), start=6):
        x0, y0, x1, y1 = bx
        lay.append(layer(lid, txt, "text", x0 / W * 100, y0 / H * 100, (x1 - x0) / W * 100, (y1 - y0) / H * 100, z,
                         text=txt, font="hn-medium", weight=500, color=hexc(labc), fit="stretch",
                         size=r2((y1 - y0) / H * 100 / 0.714)))
    d = design("01", SLUGS["01"], "TOKYO — recreation", src, orig, W, H, hexc(cream), lay)
    write_design(d, force)
    return {"split": sp, "red": hexc(redc), "cream": hexc(cream)}


# ---------------------------------------------------------------- pin 03 · pagoda sketch

def build_sketch_pin(src: str, orig: str, force: bool) -> dict:
    im = core.open_image(src).convert("RGB")
    W, H = im.size
    a = arr(im)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    yellow = (R > 190) & (G > 150) & (B < 120) & (R - B > 100)
    lum = (R + G + B) / 3

    tl = a[int(H * .02):int(H * .2), int(W * .02):int(W * .15)]
    tl_l = lum[int(H * .02):int(H * .2), int(W * .02):int(W * .15)]
    paper = median_color(tl, tl_l >= np.percentile(tl_l, 40), (238, 237, 230))
    yel = median_color(a, yellow, (242, 211, 27))

    def edges(r0, r1, fb):
        prof = yellow[int(H * r0):int(H * r1)].mean(0)
        cols = np.where(prof > .5)[0]
        return (cols[0] / W * 100, (cols[-1] + 1) / W * 100) if len(cols) > W * .03 else fb
    ux0, ux1 = edges(.05, .45, (52, 88))
    lx0, lx1 = edges(.66, .97, (52, 68))
    step = 57.0
    c0, c1 = int((lx1 + 2) / 100 * W), int((ux1 - 2) / 100 * W)
    if c1 - c0 > 4:
        seg = yellow[:, c0:c1].mean(1)
        rr = np.where(seg > .5)[0]
        if len(rr):
            step = (rr[-1] + 1) / H * 100
    band = [(ux0, 0), (ux1, 0), (ux1, step), (lx1, step), (lx1, 100), (lx0, 100), (lx0, step), (ux0, step)]

    # ink = darkening relative to the local background (paper or yellow), from R+G which both carry
    m = poly_mask(W, H, band)
    rg = (a[..., 0] + a[..., 1]).astype(np.float32) / 2
    bg = (paper[0] + paper[1]) / 2 * (1 - m) + (yel[0] + yel[1]) / 2 * m
    alpha = np.clip(1 - rg / np.maximum(bg, 1), 0, 1)
    alpha = np.clip((alpha - 0.05) / 0.95, 0, 1)

    notes_boxes = {"notes_top": (86, 2, 100, 18), "notes_bottom": (73, 72, 90, 95)}
    note_ink = {}
    for k, (x0, y0, x1, y1) in notes_boxes.items():
        sl = (slice(int(y0 / 100 * H), int(y1 / 100 * H)), slice(int(x0 / 100 * W), int(x1 / 100 * W)))
        sub = alpha[sl]
        bb = bbox(sub, 0.3, 1)
        if bb:
            note_ink[k] = (x0 + bb[0] / W * 100, y0 + bb[1] / H * 100, (bb[2] - bb[0]) / W * 100, (bb[3] - bb[1]) / H * 100)
        alpha[sl] = 0

    split, feather = 0.335 * H, 0.02 * H
    yy = np.arange(H, dtype=np.float32)[:, None]
    lower = np.clip((yy - (split - feather / 2)) / feather, 0, 1)
    ink_img = Image.new("RGB", (W, H), INK)
    t_src, t_mask, (tx, ty, tw, th) = save_cut("03", "temple-ink", ink_img, alpha * lower)
    w_src, w_mask, (wx, wy, ww, wh) = save_cut("03", "wireframe-ink", ink_img, alpha * (1 - lower))

    nt = note_ink.get("notes_top", (88.5, 4.5, 9, 10.5))
    nb = note_ink.get("notes_bottom", (75, 75, 13, 17))
    note_c = "#6b6964"
    lay = [
        layer("paper", "Paper", "rect", 0, 0, 100, 100, 0, color=hexc(paper)),
        layer("grain", "Paper grain", "svg", 0, 0, 100, 100, 1, preset="grain", opacity=0.10, blend="multiply", color="#000000"),
        layer("band", "Yellow band", "polygon", 0, 0, 100, 100, 2, color=hexc(yel), points=[[r2(x), r2(y)] for x, y in band]),
        layer("temple", "Temple + street sketch", "image", tx, ty, tw, th, 3, src=t_src, mask=t_mask, blend="multiply",
              filter="sketch", swap="sketch"),
        layer("wireframe", "Roof wireframe", "image", wx, wy, ww, wh, 4, src=w_src, mask=w_mask, blend="multiply", swap="free"),
        layer("notes_top", "Spec notes (top)", "text", nt[0], nt[1], max(nt[2], 8), nt[3], 5,
              text="FIG.03\nNYATAPOLA\n5 TIERS\nH 30.0 M\nBRICK/TIMBER\n1702 A.D.\nSCALE 1:200",
              font="menlo", size=0.75, line_height=1.35, color=note_c, tracking=40),
        layer("notes_bottom", "Spec notes (bottom)", "text", nb[0], nb[1], max(nb[2], 12), nb[3], 6,
              text="DURBAR SQUARE / KATHMANDU\n27.7045 N  85.3075 E\nSTREET LEVEL +0.00\nRICKSHAW  CYCLE  CROWD\nSECTION A-A\nREF. 03/11",
              font="menlo", size=0.75, line_height=1.45, color=note_c, tracking=30),
    ]
    d = design("03", SLUGS["03"], "Pagoda sketch — recreation", src, orig, W, H, hexc(paper), lay)
    write_design(d, force)
    return {"band": band, "paper": hexc(paper), "yellow": hexc(yel)}


# ---------------------------------------------------------------- pin 04 · look up, kid

def _ray_len(ax, ay, dx, dy, W, H):
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(dx > 1e-9, (W - 1 - ax) / dx, np.where(dx < -1e-9, -ax / dx, np.inf))
        ty = np.where(dy > 1e-9, (H - 1 - ay) / dy, np.where(dy < -1e-9, -ay / dy, np.inf))
    return np.minimum(tx, ty)


def _ray_frac(pm, ax, ay, ang_deg, r0, step):
    H, W = pm.shape
    th = np.radians(ang_deg)[:, None]
    dx, dy = np.cos(th), np.sin(th)
    rmax = _ray_len(ax, ay, dx, dy, W, H)
    rs = np.arange(r0, math.hypot(W, H), step, dtype=np.float32)[None, :]
    xs, ys = ax + dx * rs, ay + dy * rs
    valid = (rs <= rmax) & (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
    v = pm[np.clip(ys.astype(int), 0, H - 1), np.clip(xs.astype(int), 0, W - 1)] & valid
    return v.sum(1) / np.maximum(valid.sum(1), 1)


def _border_point(ax, ay, deg, W, H):
    t = math.radians(deg)
    dx, dy = math.cos(t), math.sin(t)
    s = float(_ray_len(ax, ay, np.array(dx), np.array(dy), W, H))
    return ax + dx * s, ay + dy * s


def sector_pts(ax, ay, a0, a1, W, H):
    """Polygon (px) of the fan sector a0..a1 (degrees, y down) from the apex to the canvas border."""
    corners = [(0, 0), (W - 1, 0), (W - 1, H - 1), (0, H - 1)]
    angs = [a0, a1]
    for cx, cy in corners:
        ca = math.degrees(math.atan2(cy - ay, cx - ax)) % 360
        if a0 < ca < a1:
            angs.append(ca)
    return [(ax, ay)] + [_border_point(ax, ay, g, W, H) for g in sorted(angs)]


def build_lookup(src: str, orig: str, force: bool) -> dict:
    im = core.open_image(src).convert("RGB")
    W, H = im.size
    a = arr(im)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    sat = mx - mn
    lum = (R + G + B) / 3
    paper = median_color(a, (lum > 200) & (sat < 14), (232, 232, 230))
    not_paper = np.abs(a - np.array(paper)).max(2) > 24
    pm = ~not_paper

    # apex: the point whose rays line up best with the paper gaps (searched at half size)
    hs = 2
    pm_s = pm[::hs, ::hs]
    Hs, Ws = pm_s.shape
    angs = np.arange(214, 338, 0.5)
    best, bscore = (0.45 * Ws, 0.57 * Hs), -1
    for fx in np.arange(0.37, 0.535, 0.01):
        for fy in np.arange(0.50, 0.645, 0.01):
            f = _ray_frac(pm_s, fx * Ws, fy * Hs, angs, 0.10 * Hs, 2)
            sc = float((f ** 4).sum())
            if sc > bscore:
                best, bscore = (fx * Ws, fy * Hs), sc
    ax, ay = best[0] * hs, best[1] * hs

    fine = np.arange(190, 356, 0.25)
    frac = _ray_frac(pm, ax, ay, fine, 0.10 * H, 2)
    wedges = []
    for th in (0.55, 0.45, 0.65, 0.35, 0.75):
        rs_ = [(fine[s], fine[e - 1] + 0.25) for s, e in runs(frac < th, 12)]
        if len(rs_) == 6:
            wedges = rs_
            break
        if 4 <= len(rs_) <= 8 and not wedges:
            wedges = rs_
    detected = bool(wedges)
    if not wedges:
        a0 = math.degrees(math.atan2(0.40 * H - ay, 0 - ax)) % 360
        a1 = math.degrees(math.atan2(0.45 * H - ay, W - ax)) % 360
        span = (a1 - a0) / 6
        wedges = [(a0 + i * span + 0.5, a0 + (i + 1) * span - 0.5) for i in range(6)]

    names = ["Sky + birds", "Dusk + rocket trail", "Clouds + fjord", "Aurora night", "Hot-air balloons", "Sunset clouds"]
    lay = [
        layer("paper", "Paper", "rect", 0, 0, 100, 100, 0, color=hexc(paper)),
        layer("grain", "Paper grain", "svg", 0, 0, 100, 100, 1, preset="grain", opacity=0.12, blend="multiply", color="#000000"),
    ]
    union = np.zeros((H, W), np.float32)
    for i, (a0, a1) in enumerate(wedges):
        pts = sector_pts(ax, ay, a0, a1, W, H)
        mk = poly_mask(W, H, [(x / W * 100, y / H * 100) for x, y in pts])
        union = np.maximum(union, mk)
        s, m, (x, y, w, h) = save_cut("04", f"ray-{i + 1}", im, mk)
        nm = names[i] if len(wedges) == 6 else f"Ray {i + 1}"
        lay.append(layer(f"ray{i + 1}", nm, "image", x, y, w, h, 2 + i, src=s, mask=m, swap="mask"))

    # child: non-paper below the apex, left of the text, outside the rays
    reg = np.zeros((H, W), bool)
    reg[int(ay - 0.03 * H):, :int(0.57 * W)] = True
    cm = (not_paper & reg & (union < 0.5)).astype(np.uint8) * 255
    ci = Image.fromarray(cm, "L").filter(ImageFilter.MedianFilter(5))
    pad = Image.new("L", (W + 2, H + 2), 0)
    pad.paste(ci, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    pa = np.asarray(pad, np.uint8)[1:-1, 1:-1]
    filled = np.where(pa == 128, 0, 255).astype(np.uint8)
    child_a = np.asarray(Image.fromarray(filled, "L").filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0
    cs, cmk, (cx, cy, cw, ch) = save_cut("04", "child", im, child_a)
    z = 2 + len(wedges)
    lay.append(layer("child", "Child with binoculars", "image", cx, cy, cw, ch, z, src=cs, mask=cmk, swap="cutout"))

    # orange headline lines + the grey monospace line under them
    orange = (R > 200) & (G > 90) & (G < 190) & (B < 120) & (R - B > 100)
    zone = np.zeros((H, W), bool)
    zone[int(H * .6):, int(W * .5):] = True
    o = orange & zone
    oc = median_color(a, o, (242, 140, 40))
    line_runs = [r for r in runs(o.sum(1) > 2, max(3, int(H * .01)))]
    boxes = []
    for r0, r1 in line_runs[:3]:
        cols = np.where(o[r0:r1].sum(0) > 0)[0]
        if len(cols):
            boxes.append((cols[0], r0, cols[-1] + 1, r1))
    if len(boxes) < 2:
        boxes = [(int(.58 * W), int(.73 * H), int(.92 * W), int(.775 * H)), (int(.58 * W), int(.78 * H), int(.72 * W), int(.82 * H))]
    texts = ["LOOK UP,", "KID"]
    for i, (x0, y0, x1, y1) in enumerate(boxes[:2]):
        z += 1
        lay.append(layer(f"head{i + 1}", texts[i], "text", x0 / W * 100, y0 / H * 100, (x1 - x0) / W * 100, (y1 - y0) / H * 100, z,
                         text=texts[i], font="futura-cond-xb", weight=800, color=hexc(oc), fit="stretch",
                         effect="inline", effect_color=hexc(paper), size=r2((y1 - y0) / H * 100 / 0.72)))
    ob = max(b[3] for b in boxes[:2])
    sub = (mx < 150) & (sat < 45) & ~orange
    sz = np.zeros((H, W), bool)
    sz[ob + int(H * .004):int(H * .99), int(W * .55):int(W * .99)] = True
    sb = bbox((sub & sz).astype(np.float32), 0.5, 2)
    if not sb or (sb[3] - sb[1]) > H * .12:
        sb = (boxes[0][0], ob + int(H * .015), boxes[0][0] + int(W * .3), ob + int(H * .055))
    subc = median_color(a, sub & sz & (mx < 120), (70, 70, 70))
    z += 1
    lay.append(layer("tagline", "Tagline", "text", sb[0] / W * 100, sb[1] / H * 100, (sb[2] - sb[0]) / W * 100, (sb[3] - sb[1]) / H * 100, z,
                     text="The world is wider than\nthey told you", font="courier", color=hexc(subc), fit="stretch",
                     line_height=1.35, size=1.4))
    d = design("04", SLUGS["04"], "Look up, kid — recreation", src, orig, W, H, hexc(paper), lay,
               notes="" if detected else "Ray gaps not detected; rays split evenly from the apex.")
    write_design(d, force)
    return {"apex": [r2(ax / W * 100), r2(ay / H * 100)], "rays": len(wedges), "detected": detected}


# ---------------------------------------------------------------- Bali photos

def features(path: str) -> dict:
    im = core.open_image(core.thumb(path, 320))
    a = np.asarray(im.convert("RGB"), np.float32)
    h, w = a.shape[:2]
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    L = (R + G + B) / 3
    top = slice(0, int(h * .4))
    mid = slice(int(h * .35), int(h * .75))
    gy, gx = np.abs(np.diff(L, axis=0))[:, :-1], np.abs(np.diff(L, axis=1))[:-1, :]
    grad = gy + gx
    ch = grad[int(h * .25):int(h * .9), int(w * .2):int(w * .8)]
    return {
        "sky": float(((B > R + 12) & (B > 110))[top].mean()),
        "bright_top": float((L[top] > 170).mean()),
        "sunset": float(((R > 170) & (R - B > 60) & (G > 70)).mean()),
        "green": float(((G > R + 8) & (G > B + 8) & (G > 60)).mean()),
        "ocean": float(((B > R + 20) & (B > G - 5) & (B > 90))[mid].mean()),
        "detail": float((ch > 40).mean()),
        "smooth_top": float((grad[: int(h * .3)] < 12).mean()),
        "lum": float(L.mean() / 255),
        "portrait": h > w,
    }


def pick_bali(index: list[dict]) -> dict:
    """index: date-sorted [{path, date, place, f:{features}}]. Returns role → entry."""
    ok = [e for e in index if e.get("f")]
    if not ok:
        return {}
    used: set = set()

    def take(role_score, exclude_early=0):
        cands = [(role_score(e), i, e) for i, e in enumerate(ok) if e["path"] not in used and i >= exclude_early]
        if not cands:
            cands = [(role_score(e), i, e) for i, e in enumerate(ok) if e["path"] not in used]
        if not cands:
            return None
        cands.sort(key=lambda t: -t[0])
        used.add(cands[0][2]["path"])
        return cands[0][2]

    picks = {}
    if len(ok) >= 5:
        picks["plane_sky"] = ok[4]
        used.add(ok[4]["path"])
    else:
        picks["plane_sky"] = take(lambda e: e["f"]["sky"] + e["f"]["smooth_top"] * .5)
    early = 6 if len(ok) > 20 else 0
    temple_place = lambda e: 1.5 if (e.get("place") in core.TEMPLE_PLACES) else 0  # noqa: E731
    picks["temple"] = take(lambda e: temple_place(e) + 1.2 * e["f"]["detail"] + .8 * max(e["f"]["sky"], e["f"]["bright_top"])
                           + .6 * e["f"]["smooth_top"] + (.3 if e["f"]["portrait"] else 0) - 1.5 * e["f"]["sunset"]
                           - .8 * e["f"]["green"], early)
    picks["sketch"] = take(lambda e: temple_place(e) + 1.5 * e["f"]["detail"] + (.2 if e["f"]["portrait"] else 0)
                           - e["f"]["sunset"] - .4 * e["f"]["green"], early)
    picks["sunset"] = take(lambda e: 2 * e["f"]["sunset"] + .2 * e["f"]["sky"] - .3 * e["f"]["green"], early)
    picks["landscape"] = take(lambda e: e["f"]["ocean"] + .9 * e["f"]["green"] + .4 * e["f"]["sky"] - .5 * e["f"]["detail"], early)
    return {k: v for k, v in picks.items() if v}


# ---------------------------------------------------------------- cut-outs and sketches (also used by cutout.py / sketch.py)

def sky_mask(im: Image.Image) -> np.ndarray:
    """1 = subject, 0 = sky connected to the top edge (bright / bluish, smooth)."""
    small = im.convert("RGB").copy()
    small.thumbnail((420, 420), Image.LANCZOS)
    a = np.asarray(small, np.float32)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    L = (R + G + B) / 3
    Lb = np.asarray(Image.fromarray(L.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32)
    grad = np.zeros_like(Lb)
    grad[:-1, :-1] = np.abs(np.diff(Lb, axis=0))[:, :-1] + np.abs(np.diff(Lb, axis=1))[:-1, :]
    cand = (((B >= R - 8) & (L > 115)) | (L > 205)) & (grad < 14)
    ci = Image.fromarray((cand * 255).astype(np.uint8), "L")
    for x in range(0, ci.width, 3):
        if ci.getpixel((x, 0)) == 255:
            ImageDraw.floodfill(ci, (x, 0), 128)
    sky = np.asarray(ci, np.uint8) == 128
    subj = Image.fromarray((~sky * 255).astype(np.uint8), "L").filter(ImageFilter.MedianFilter(5))
    subj = subj.resize(im.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.0))
    return np.asarray(subj, np.float32) / 255.0


def vignette(w: int, h: int, fade: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.minimum(xx, w - 1 - xx) / max(1.0, w * fade)
    dy = np.minimum(yy, h - 1 - yy) / max(1.0, h * fade)
    t = np.clip(np.minimum(dx, dy), 0, 1)
    return t * t * (3 - 2 * t)


def bw_tone(im: Image.Image, contrast: float = 1.25) -> Image.Image:
    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    a = (np.asarray(g, np.float32) / 255 - 0.5) * contrast + 0.5
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L").convert("RGB")


def cutout(src: str, mode: str = "auto", region=None, polygon=None, bw: bool = False, max_side: int = 1800):
    """Cut a subject from a photo. Returns (RGBA image, info). region = (x, y, w, h) in % of the photo."""
    im = core.open_image(src, max_side).convert("RGB")
    if region:
        x, y, w, h = region
        W, H = im.size
        box = (int(x / 100 * W), int(y / 100 * H), int((x + w) / 100 * W), int((y + h) / 100 * H))
        if box[2] - box[0] > 4 and box[3] - box[1] > 4:
            im = im.crop(box)
    W, H = im.size
    info = {"mode": mode}
    if polygon:
        alpha = poly_mask(W, H, polygon)
        info["mode"] = "polygon"
    elif mode == "rect":
        alpha = np.ones((H, W), np.float32)
    elif mode == "vignette":
        alpha = vignette(W, H, 0.12)
    else:
        alpha = sky_mask(im)
        frac = 1 - float(alpha.mean())
        info["sky_removed"] = round(frac, 3)
        if frac < 0.04:
            alpha = vignette(W, H, 0.12)
            info["mode"] = "vignette (no sky found)"
        else:
            info["mode"] = "sky"
            alpha = alpha * np.clip(vignette(W, H, 0.04) * 1.0 + (np.arange(H)[:, None] > H * .5), 0, 1)
    rgbim = bw_tone(im) if bw else im
    a8 = Image.fromarray(np.clip(alpha * 255, 0, 255).astype(np.uint8), "L")
    out = rgbim.copy()
    out.putalpha(a8)
    bb = a8.point(lambda v: 255 if v > 8 else 0).getbbox()
    if bb:
        out = out.crop(bb)
    return out, info


def sketch(src: str, strength: float = 1.0, fade: float = 0.18, max_side: int = 1400) -> Image.Image:
    """Pencil/ink sketch as dark ink on transparent: grayscale + contrast + dodge lines + edges, faded edges."""
    src_im = core.open_image(src, max_side)
    src_alpha = np.asarray(src_im.getchannel("A"), np.float32) / 255 if src_im.mode == "RGBA" else None
    im = src_im.convert("RGB")
    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    ga = np.asarray(g, np.float32)
    inv = Image.fromarray((255 - ga).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(max(2.0, g.width / 160)))
    ib = np.asarray(inv, np.float32)
    dodge = np.clip(ga * 255 / np.maximum(255 - ib, 1), 0, 255)
    shade = dodge * (0.6 + 0.4 * ga / 255)
    ink = 1 - shade / 255
    edges = np.asarray(g.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255
    ink = np.clip((ink * 1.7 + edges * 0.6) * strength, 0, 1)
    ink = np.clip((ink - 0.06) / 0.94, 0, 1)
    ink *= vignette(g.width, g.height, max(0.01, fade))
    if src_alpha is not None:  # a cut-out keeps its shape: no sketch where the source was transparent
        ink *= src_alpha
    out = Image.new("RGB", g.size, INK)
    out.putalpha(Image.fromarray((ink * 255).astype(np.uint8), "L"))
    return out


# ---------------------------------------------------------------- Bali variants

def _box_fit(W, H, iw, ih, zone, anchor="bottom"):
    """(x, y, w, h)% of an iw×ih image fitted inside zone (x0, y0, x1, y1)% of a W×H canvas."""
    zx0, zy0, zx1, zy1 = zone
    zw, zh = (zx1 - zx0) / 100 * W, (zy1 - zy0) / 100 * H
    k = min(zw / iw, zh / ih)
    w, h = iw * k, ih * k
    x = (zx0 / 100 * W) + (zw - w) / 2
    y = (zy1 / 100 * H) - h if anchor == "bottom" else (zy0 / 100 * H) + (zh - h) / 2
    return x / W * 100, y / H * 100, w / W * 100, h / H * 100


def _variant(base: dict, suffix_name: str) -> dict:
    v = copy.deepcopy(base)
    v["slug"] = base["slug"] + "-bali"
    v["name"] = suffix_name
    v["variant_of"] = base["slug"]
    v["created"] = v["updated"] = core.now_iso()
    return v


def _lay(d: dict, lid: str) -> dict:
    return next(L for L in d["layers"] if L["id"] == lid)


def build_bali(picks: dict, force: bool) -> dict:
    out = {}
    W_ = lambda d: d["canvas"]["width"]  # noqa: E731
    H_ = lambda d: d["canvas"]["height"]  # noqa: E731

    base = core.read_json(os.path.join(core.d("originals"), SLUGS["01"] + ".json"))
    if base and picks.get("temple"):
        p = picks["temple"]
        img, info = cutout(p["path"], "auto", bw=True)
        cut = core.save_png(img, os.path.join(core.d("cutouts"), f"bali-temple-{core.file_key(p['path'])[:8]}.png"))
        v = _variant(base, "TOKYO — Bali variant")
        W, H = W_(v), H_(v)
        pg = _lay(v, "pagoda")
        x, y, w, h = _box_fit(W, H, img.width, img.height, (14, 4, 86, 82))
        pg.update(src=cut, src_raw=cut, mask="", x=r2(x), y=r2(y), w=r2(w), h=r2(h), name="Bali temple cut-out", fit="fill")
        place = (p.get("place") or "UBUD").upper()
        if place in ("BALI", "BALI AIRPORT"):
            place = "UBUD"
        _lay(v, "tokyo")["text"] = "BALI"
        for lid, txt, align in (("asakusa", place, "left"), ("japan", "INDONESIA", "right")):
            L = _lay(v, lid)
            size = L["h"] / 0.714
            L.update(text=txt, name=txt, fit="none", size=r2(size), align=align, line_height=1)
            # keep the cap line where it was: baseline = top + (0.5 + 0.35) * size
            base_y = L["y"] + L["h"]
            L["y"] = r2(base_y - 0.85 * size)
            L["h"] = r2(size)
            if align == "right":
                right = L["x"] + L["w"]
                L["w"] = 40.0
                L["x"] = r2(right - 40.0)
            else:
                L["w"] = 40.0
        v["notes"] = f"Temple photo: {os.path.basename(p['path'])} ({info['mode']})."
        write_design(v, force)
        out["01"] = v["slug"]

    base = core.read_json(os.path.join(core.d("originals"), SLUGS["03"] + ".json"))
    if base and (picks.get("sketch") or picks.get("temple")):
        p = picks.get("sketch") or picks["temple"]
        img = sketch(p["path"])
        sk = core.save_png(img, os.path.join(core.d("cutouts"), f"bali-sketch-{core.file_key(p['path'])[:8]}.png"))
        v = _variant(base, "Pagoda sketch — Bali variant")
        W, H = W_(v), H_(v)
        t = _lay(v, "temple")
        x, y, w, h = _box_fit(W, H, img.width, img.height, (8, 30, 84, 97))
        t.update(src=sk, src_raw=core.web_copy(p["path"]), mask="", x=r2(x), y=r2(y), w=r2(w), h=r2(h),
                 name="Bali sketch", fit="fill")
        _lay(v, "band")["color"] = "#e8b21a"
        _lay(v, "notes_bottom")["text"] = f"{(p.get('place') or 'BALI').upper()} / INDONESIA\n-8.5069 S  115.2625 E\nSTREET LEVEL +0.00\nSCOOTER  OFFERING  GATE\nSECTION B-B\nREF. 03/11-B"
        v["notes"] = f"Sketch photo: {os.path.basename(p['path'])}."
        write_design(v, force)
        out["03"] = v["slug"]

    base = core.read_json(os.path.join(core.d("originals"), SLUGS["04"] + ".json"))
    if base:
        v = _variant(base, "Look up, kid — Bali variant")
        swaps = [("ray1", "plane_sky", "Bali · plane-window sky"), ("ray3", "landscape", "Bali · coast / terraces"),
                 ("ray6", "sunset", "Bali · sunset")]
        used = []
        for lid, role, nm in swaps:
            p = picks.get(role)
            if not p or not any(L["id"] == lid for L in v["layers"]):
                continue
            L = _lay(v, lid)
            web = core.web_copy(p["path"])
            L.update(src=web, src_raw=web, fit="cover", crop={"x": 50, "y": 50, "scale": 1}, name=nm)
            used.append(os.path.basename(p["path"]))
        v["notes"] = "Rays swapped: " + ", ".join(used)
        write_design(v, force)
        out["04"] = v["slug"]
    return out
