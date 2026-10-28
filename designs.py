"""Design store for Pin Remake: list, read, save, draft, save-as-variant, duplicate, revert, delete.

Designs live in ~/Fused/pin-remake/designs/<slug>.json; unsaved edits in drafts/<slug>.json;
the shipped layouts (for "Revert to original layout") in originals/<slug>.json.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pinlib import core, fonts  # noqa: E402

ACTIONS = ("list", "get", "save", "draft", "discard", "save_as", "duplicate", "revert", "delete")


def _p(kind: str, slug: str) -> str:
    return os.path.join(core.d(kind), core.slugify(slug) + ".json")


def _load(slug: str):
    return core.read_json(_p("designs", slug))


def _current(slug: str):
    """(design, has_draft) — the draft when there is one."""
    dr = core.read_json(_p("drafts", slug))
    return (dr, True) if dr else (_load(slug), False)


def _unique(slug: str) -> str:
    base, n, s = core.slugify(slug), 2, core.slugify(slug)
    while os.path.exists(_p("designs", s)):
        s = f"{base}-{n}"
        n += 1
    return s


def _parse(design: str) -> dict:
    d = json.loads(design) if isinstance(design, str) else design
    if not isinstance(d, dict) or not isinstance(d.get("layers"), list) or not isinstance(d.get("canvas"), dict):
        raise ValueError("design must be a JSON object with `canvas` and `layers`.")
    return d


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _root_original(slug: str):
    seen = set()
    while slug and slug not in seen:
        seen.add(slug)
        o = core.read_json(_p("originals", slug))
        if o:
            return o
        d = _load(slug)
        slug = (d or {}).get("variant_of")
    return None


def main(action: str = "list", slug: str = "", design: str = "", name: str = "") -> dict:
    core.ensure_dirs()
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")

    if action == "list":
        idx = core.read_json(os.path.join(core.d("sources"), "index.json"), {}) or {}
        out = []
        for fn in sorted(os.listdir(core.d("designs"))):
            if not fn.endswith(".json"):
                continue
            s = fn[:-5]
            d, has_draft = _current(s)
            if not d:
                continue
            d["slug"] = s
            out.append({"slug": s, "name": d.get("name", s), "pin": d.get("pin"), "variant_of": d.get("variant_of"),
                        "updated": d.get("updated"), "has_draft": has_draft,
                        "shipped": os.path.isfile(_p("originals", s)), "design": d})
        try:
            built = int(os.path.getmtime(os.path.join(core.ROOT, "setup.json")))
        except OSError:
            built = 0
        return {"root": core.ROOT, "pins": idx.get("pins", []), "roles": idx.get("roles", {}),
                "designs": out, "fonts": fonts.table(), "bali_dir": core.BALI_DIR, "built": built}

    if not slug:
        raise ValueError("slug is required")
    slug = core.slugify(slug)

    if action == "get":
        d, has_draft = _current(slug)
        if not d:
            raise FileNotFoundError(f"No design '{slug}'")
        return {"design": d, "has_draft": has_draft}

    if action == "save":
        d = _parse(design) if design else _current(slug)[0]
        if not d:
            raise FileNotFoundError(f"No design '{slug}'")
        d["slug"], d["updated"] = slug, core.now_iso()
        core.write_json(_p("designs", slug), d)
        _rm(_p("drafts", slug))
        return {"ok": True, "slug": slug, "design": d}

    if action == "draft":
        d = _parse(design)
        d["slug"], d["updated"] = slug, core.now_iso()
        core.write_json(_p("drafts", slug), d)
        return {"ok": True, "slug": slug}

    if action == "discard":
        _rm(_p("drafts", slug))
        return {"ok": True, "design": _load(slug)}

    if action in ("save_as", "duplicate"):
        src = _parse(design) if design else _current(slug)[0]
        if not src:
            raise FileNotFoundError(f"No design '{slug}'")
        label = (name or "").strip() or (src.get("name", slug) + (" variant" if action == "save_as" else " copy"))
        new = _unique(name or (slug + ("-variant" if action == "save_as" else "-copy")))
        d = json.loads(json.dumps(src))
        d.update(slug=new, name=label, created=core.now_iso(), updated=core.now_iso())
        d["variant_of"] = slug if action == "save_as" else (src.get("variant_of") or slug)
        core.write_json(_p("designs", new), d)
        if action == "save_as":
            _rm(_p("drafts", slug))
        return {"ok": True, "slug": new, "design": d}

    if action == "revert":
        cur, _ = _current(slug)
        orig = _root_original(slug)
        if not orig:
            raise FileNotFoundError(f"No original layout for '{slug}'")
        d = json.loads(json.dumps(orig))
        if cur:
            for k in ("slug", "name", "variant_of", "created"):
                if k in cur:
                    d[k] = cur[k]
        d["slug"], d["updated"] = slug, core.now_iso()
        core.write_json(_p("drafts", slug), d)
        return {"ok": True, "design": d, "has_draft": True}

    # delete — only designs the user made; shipped ones come back on the next setup run anyway
    if os.path.isfile(_p("originals", slug)):
        raise PermissionError("Shipped designs cannot be deleted; use revert instead.")
    _rm(_p("designs", slug))
    _rm(_p("drafts", slug))
    return {"ok": True, "slug": slug}
