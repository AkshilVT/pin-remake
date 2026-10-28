"""Render a design to a full-resolution PNG in ~/Fused/pin-remake/exports/<slug>.png."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pinlib import core, render  # noqa: E402


def main(slug: str, scale: float = 1.0, draft: bool = True) -> dict:
    t0 = time.monotonic()
    core.ensure_dirs()
    s = core.slugify(slug)
    d = core.read_json(os.path.join(core.d("drafts"), s + ".json")) if draft else None
    d = d or core.read_json(os.path.join(core.d("designs"), s + ".json"))
    if not d:
        raise FileNotFoundError(f"No design '{s}'")
    scale = max(0.25, min(float(scale), 4.0))
    img = render.render(d, scale)
    out = os.path.join(core.d("exports"), f"{s}.png" if scale == 1 else f"{s}@{scale:g}x.png")
    core.save_png(img, out)
    return {"png": out, "width": img.width, "height": img.height, "seconds": round(time.monotonic() - t0, 2)}
