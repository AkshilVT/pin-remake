"""Turn a photo into a pencil/ink sketch (dark ink on transparent, faded edges) under ~/Fused/pin-remake/cutouts/."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

from pinlib import build, core  # noqa: E402


def main(src: str, strength: float = 1.0, fade: float = 0.18) -> dict:
    core.ensure_dirs()
    path = core.expand(src)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    strength = max(0.2, min(float(strength), 3.0))
    fade = max(0.0, min(float(fade), 0.5))
    k = core.file_key(path, "sketch-v1", round(strength, 3), round(fade, 3))
    out = os.path.join(core.d("cutouts"), f"{core.slugify(os.path.splitext(os.path.basename(path))[0])}-sketch-{k[:10]}.png")
    if os.path.isfile(out):
        im = Image.open(out)
    else:
        im = build.sketch(path, strength, fade)
        core.save_png(im, out)
    return {"png": out, "width": im.width, "height": im.height, "raw": core.web_copy(path)}
