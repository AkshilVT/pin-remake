"""Store an image picked in the browser (base64) under ~/Fused/pin-remake/uploads/ so layers can use it."""

from __future__ import annotations

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pinlib import core  # noqa: E402

OK_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def main(name: str, data: str) -> dict:
    core.ensure_dirs()
    base, ext = os.path.splitext(os.path.basename(name or "upload.jpg"))
    ext = ext.lower()
    if ext not in OK_EXT:
        raise ValueError(f"Unsupported file type '{ext}'.")
    raw = base64.b64decode(data.split(",", 1)[1] if data.startswith("data:") else data)
    if len(raw) > 60_000_000:
        raise ValueError("File is larger than 60 MB.")
    out = os.path.join(core.d("uploads"), f"{core.slugify(base)}-{core.key(len(raw), raw[:4096].hex())[:8]}{ext}")
    core.write_atomic(out, raw)
    return {"path": out, "web": core.web_copy(out), "bytes": len(raw)}
