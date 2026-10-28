"""First-run build for Pin Remake, resumable in ≤ 40 s slices.

Copies the Pinterest pins into ~/Fused/pin-remake/sources/, cuts the Phase 1 pins (01, 03, 04) into layers,
indexes the Bali folder, picks Bali photos and writes the 6 designs. Call again while it answers
`status: "running"`; finished steps are remembered in ~/Fused/pin-remake/setup.json.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pinlib import build, core  # noqa: E402

SETUP_V = 3
BUDGET_S = 38.0
STEPS = [
    ("sources", "Copying the Pinterest pins"),
    ("pin01", "Cutting pin 01 · TOKYO"),
    ("pin03", "Cutting pin 03 · pagoda sketch"),
    ("pin04", "Cutting pin 04 · look up, kid"),
    ("bali_index", "Looking through the Bali photos"),
    ("bali_build", "Building the Bali variants"),
]
STATE = os.path.join(core.ROOT, "setup.json")
BALI_INDEX = os.path.join(core.ROOT, "cache", "bali-index.json")


def _sources() -> dict:
    idx_path = os.path.join(core.d("sources"), "index.json")
    if not os.path.isdir(core.PINS_DIR):
        prev = core.read_json(idx_path)
        if prev:
            return {"pins": len(prev.get("pins", [])), "note": "Pin folder missing; using earlier copies."}
        raise FileNotFoundError(f"No pins found: {core.PINS_DIR} does not exist.")
    files = [p for p in core.list_images(core.PINS_DIR)]
    files.sort(key=lambda p: (os.stat(p).st_mtime_ns, os.path.basename(p)))
    pins = []
    for i, p in enumerate(files, start=1):
        n = f"{i:02d}"
        src_ext = os.path.splitext(p)[1].lower()
        if src_ext in (".jpg", ".jpeg", ".png", ".webp"):
            dst = os.path.join(core.d("sources"), n + src_ext)
            core.copy_if_changed(p, dst)
        else:  # HEIC → JPEG
            dst = os.path.join(core.d("sources"), n + ".jpg")
            core.save_jpg(core.open_image(p), dst)
        w, h = core.open_image(dst, 0).size
        pins.append({"n": n, "file": dst, "original": p, "name": os.path.basename(p), "w": w, "h": h,
                     "mtime": os.stat(p).st_mtime, "title": core.PIN_TITLES.get(n, f"Pin {n}"),
                     "scores": build.pin_scores(dst)})
    roles = build.assign_roles(pins)
    core.write_json(idx_path, {"pins": pins, "roles": roles, "folder": core.PINS_DIR, "updated": core.now_iso()})
    return {"pins": len(pins), "roles": roles}


def _pin(pin: str, force: bool) -> dict:
    idx = core.read_json(os.path.join(core.d("sources"), "index.json"), {}) or {}
    n = (idx.get("roles") or {}).get(pin) or pin
    ent = next((p for p in idx.get("pins", []) if p["n"] == n), None)
    if not ent:
        return {"skipped": f"no source for pin {pin}"}
    fn = {"01": build.build_tokyo, "03": build.build_sketch_pin, "04": build.build_lookup}[pin]
    return fn(ent["file"], ent["original"], force)


def _bali_index(t0: float) -> tuple[bool, dict]:
    if not os.path.isdir(core.BALI_DIR):
        return True, {"photos": 0, "note": f"{core.BALI_DIR} not found"}
    files = core.list_images(core.BALI_DIR)
    index = core.read_json(BALI_INDEX, {}) or {}
    fresh, done = {}, 0
    for p in files:
        st = os.stat(p)
        e = index.get(p)
        if not e or e.get("m") != st.st_mtime_ns or e.get("s") != st.st_size or "f" not in e:
            if time.monotonic() - t0 > BUDGET_S:
                fresh.update({k: v for k, v in index.items() if k in files and k not in fresh})
                core.write_json(BALI_INDEX, fresh)
                return False, {"indexed": done, "found": len(files)}
            try:
                e = core.photo_meta(p)
                e["f"] = build.features(p)
            except Exception as err:  # noqa: BLE001 — unreadable photo: keep a stub so it is not retried forever
                st2 = os.stat(p)
                e = {"m": st2.st_mtime_ns, "s": st2.st_size, "err": str(err)[:160], "f": None, "date": ""}
        fresh[p] = e
        done += 1
    core.write_json(BALI_INDEX, fresh)
    return True, {"photos": len(fresh)}


def _bali_build(force: bool) -> dict:
    index = core.read_json(BALI_INDEX, {}) or {}
    entries = [dict(v, path=k) for k, v in index.items() if v.get("f")]
    entries.sort(key=lambda e: (e.get("date") or "", os.path.basename(e["path"]).lower()))
    picks = build.pick_bali(entries)
    made = build.build_bali(picks, force)
    return {"picks": {k: os.path.basename(v["path"]) for k, v in picks.items()},
            "pick_paths": {k: v["path"] for k, v in picks.items()}, "designs": made}


def main(force: bool = False, rebuild: str = "") -> dict:
    t0 = time.monotonic()
    core.ensure_dirs()
    st = core.read_json(STATE, {}) or {}
    if st.get("v") != SETUP_V or force:
        st = {"v": SETUP_V, "done": {}, "force": bool(force)}
    for s in [s.strip() for s in (rebuild or "").split(",") if s.strip()]:
        st["done"].pop(s, None)
        st["force"] = True
    redo = bool(st.get("force"))
    for i, (step, label) in enumerate(STEPS):
        if step in st["done"]:
            continue
        # resumable steps run until the budget; the others must start early enough to finish under the 60 s kill
        limit = BUDGET_S if step == "bali_index" else 15.0
        if time.monotonic() - t0 > limit:
            core.write_json(STATE, st)
            return {"status": "running", "step": step, "message": label, "progress": i / len(STEPS)}
        try:
            if step == "sources":
                res = _sources()
            elif step.startswith("pin"):
                res = _pin(step[3:], redo)
            elif step == "bali_index":
                finished, res = _bali_index(t0)
                if not finished:
                    core.write_json(STATE, st)
                    return {"status": "running", "step": step,
                            "message": f"{label} ({res['indexed']}/{res['found']})", "progress": (i + 0.5) / len(STEPS)}
            else:
                res = _bali_build(redo)
        except Exception as err:  # noqa: BLE001 — report which step broke; later steps still run
            print(f"[setup] {step} failed: {err}")
            res = {"error": f"{type(err).__name__}: {err}"}
            if step == "sources":
                core.write_json(STATE, st)
                return {"status": "error", "step": step, "message": res["error"], "progress": 0}
        st["done"][step] = res
        core.write_json(STATE, st)
    if st.get("force"):
        st["force"] = False
        core.write_json(STATE, st)
    return {"status": "done", "root": core.ROOT, "steps": st["done"], "progress": 1}
