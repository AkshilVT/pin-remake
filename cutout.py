"""Cut a region / subject out of a photo into a transparent PNG (+ its mask) under ~/Fused/pin-remake/cutouts/."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

from pinlib import build, core  # noqa: E402

MODES = ("auto", "sky", "polygon", "rect", "vignette")


def main(src: str, mode: str = "auto", x: float = 0, y: float = 0, w: float = 100, h: float = 100,
         polygon: str = "", bw: bool = False) -> dict:
    core.ensure_dirs()
    path = core.expand(src)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    pts = json.loads(polygon) if polygon else None
    if mode == "polygon" and not pts:
        raise ValueError("mode 'polygon' needs `polygon`: a JSON list of [x, y] points in % of the region.")
    region = None if (x, y, w, h) == (0, 0, 100, 100) else (x, y, w, h)
    k = core.file_key(path, mode, x, y, w, h, polygon, bw)
    out = os.path.join(core.d("cutouts"), f"{core.slugify(os.path.splitext(os.path.basename(path))[0])}-{k[:10]}.png")
    mask = out[:-4] + "-mask.png"
    if not (os.path.isfile(out) and os.path.isfile(mask)):
        img, info = build.cutout(path, "auto" if mode in ("auto", "sky") else mode, region=region, polygon=pts, bw=bw)
        core.save_png(img, out)
        m = Image.new("RGBA", img.size, (255, 255, 255, 0))
        m.putalpha(img.getchannel("A"))
        core.save_png(m, mask)
        mode_used = info.get("mode", mode)
    else:
        img = Image.open(out)
        mode_used = mode
    return {"png": out, "mask": mask, "width": img.width, "height": img.height, "mode": mode_used}
