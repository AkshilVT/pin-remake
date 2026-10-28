"""List a photo folder (date-sorted) with cached thumbnails — the Swap image browser and bots use it."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pinlib import core  # noqa: E402

BUDGET_S = 40.0


def main(path: str = "", offset: int = 0, count: int = 60, size: int = 320) -> dict:
    t0 = time.monotonic()
    core.ensure_dirs()
    folder = core.expand(path) if path and path.strip() else core.BALI_DIR
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"No such folder: {folder}")
    offset, count, size = max(0, int(offset)), max(1, min(int(count), 200)), max(96, min(int(size), 800))

    ipath = os.path.join(core.d("cache"), "folders", core.key(folder) + ".json")
    index = core.read_json(ipath, {}) or {}
    files = core.list_images(folder)
    fresh, dirty = {}, False
    for i, p in enumerate(files):
        st = os.stat(p)
        e = index.get(p)
        if not e or e.get("m") != st.st_mtime_ns or e.get("s") != st.st_size:
            if time.monotonic() - t0 > BUDGET_S:  # big first scan: keep progress, ask to be called again
                fresh.update({q: index[q] for q in files[i:] if q in index})
                core.write_json(ipath, fresh)
                return {"folder": folder, "total": len(files), "offset": offset, "photos": [], "next_offset": offset,
                        "status": "indexing", "indexed": i, "heic_supported": True}
            try:
                e = core.photo_meta(p)
            except Exception as err:  # noqa: BLE001
                e = {"m": st.st_mtime_ns, "s": st.st_size, "date": "", "err": str(err)[:120]}
            dirty = True
        fresh[p] = e
    if dirty or len(fresh) != len(index):
        core.write_json(ipath, fresh)

    ordered = sorted(fresh.items(), key=lambda it: (it[1].get("date") or "", os.path.basename(it[0]).lower()))
    photos, k = [], offset
    end = min(len(ordered), offset + count)
    while k < end:
        if photos and time.monotonic() - t0 > BUDGET_S:
            break
        p, e = ordered[k]
        k += 1
        try:
            th = core.thumb(p, size)
        except Exception as err:  # noqa: BLE001
            print(f"[list_folder] {p}: {err}")
            continue
        photos.append({"path": p, "name": os.path.basename(p), "n": k, "date": e.get("date"), "place": e.get("place"),
                       "w": e.get("w"), "h": e.get("h"), "thumb": th})
    return {"folder": folder, "total": len(ordered), "offset": offset, "photos": photos, "status": "ok",
            "next_offset": k if k < len(ordered) else None, "heic_supported": True}
