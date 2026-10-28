"""Make a browser-ready copy of any photo (HEIC → JPEG, long side ≤ max_side) under ~/Fused/pin-remake/photos/."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

from pinlib import core  # noqa: E402


def main(src: str, max_side: int = 2400) -> dict:
    core.ensure_dirs()
    path = core.expand(src)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    out = core.web_copy(path, max(400, min(int(max_side), 6000)))
    with Image.open(out) as im:
        w, h = im.size
    return {"path": out, "width": w, "height": h}
