"""The font table shared by the page (CSS @font-face via local()) and the PNG exporter (PIL)."""

from __future__ import annotations

import os

from PIL import ImageFont

SUP = "/System/Library/Fonts/Supplemental"
SYS = "/System/Library/Fonts"

# id, label, family + style as PIL's getname() reports them, file, CSS local() names, CSS fallback stack
FONTS = [
    ("hn-cond-black", "Helvetica Neue Condensed Black", "Helvetica Neue", "Condensed Black", f"{SYS}/HelveticaNeue.ttc",
     ["HelveticaNeue-CondensedBlack", "Helvetica Neue Condensed Black"], "Impact, 'Arial Narrow', sans-serif"),
    ("hn-cond-bold", "Helvetica Neue Condensed Bold", "Helvetica Neue", "Condensed Bold", f"{SYS}/HelveticaNeue.ttc",
     ["HelveticaNeue-CondensedBold", "Helvetica Neue Condensed Bold"], "'Arial Narrow', sans-serif"),
    ("hn-bold", "Helvetica Neue Bold", "Helvetica Neue", "Bold", f"{SYS}/HelveticaNeue.ttc",
     ["HelveticaNeue-Bold", "Helvetica Neue Bold"], "Helvetica, Arial, sans-serif"),
    ("hn-medium", "Helvetica Neue Medium", "Helvetica Neue", "Medium", f"{SYS}/HelveticaNeue.ttc",
     ["HelveticaNeue-Medium", "Helvetica Neue Medium"], "Helvetica, Arial, sans-serif"),
    ("hn-light", "Helvetica Neue Light", "Helvetica Neue", "Light", f"{SYS}/HelveticaNeue.ttc",
     ["HelveticaNeue-Light", "Helvetica Neue Light"], "Helvetica, Arial, sans-serif"),
    ("impact", "Impact", "Impact", "Regular", f"{SUP}/Impact.ttf", ["Impact"], "sans-serif"),
    ("din-cond", "DIN Condensed Bold", "DIN Condensed", "Bold", f"{SUP}/DIN Condensed Bold.ttf",
     ["DINCondensed-Bold", "DIN Condensed Bold"], "'Arial Narrow', sans-serif"),
    ("avenir-cond-heavy", "Avenir Next Condensed Heavy", "Avenir Next Condensed", "Heavy", f"{SYS}/Avenir Next Condensed.ttc",
     ["AvenirNextCondensed-Heavy", "Avenir Next Condensed Heavy"], "'Arial Narrow', sans-serif"),
    ("futura-bold", "Futura Bold", "Futura", "Bold", f"{SUP}/Futura.ttc", ["Futura-Bold", "Futura Bold"], "sans-serif"),
    ("futura-cond-xb", "Futura Condensed ExtraBold", "Futura", "Condensed ExtraBold", f"{SUP}/Futura.ttc",
     ["Futura-CondensedExtraBold", "Futura Condensed ExtraBold"], "sans-serif"),
    ("rockwell-bold", "Rockwell Bold", "Rockwell", "Bold", f"{SUP}/Rockwell.ttc", ["Rockwell-Bold", "Rockwell Bold"], "serif"),
    ("courier", "Courier New", "Courier New", "Regular", f"{SUP}/Courier New.ttf", ["CourierNewPSMT", "Courier New"], "monospace"),
    ("menlo", "Menlo", "Menlo", "Regular", f"{SYS}/Menlo.ttc", ["Menlo-Regular", "Menlo"], "ui-monospace, monospace"),
]
BY_ID = {f[0]: f for f in FONTS}
DEFAULT = "hn-medium"


def table() -> list[dict]:
    return [{"id": f[0], "label": f[1], "local": f[5], "fallback": f[6], "available": os.path.isfile(f[4])} for f in FONTS]


_index_cache: dict = {}


def _index(fid: str) -> tuple[str, int] | None:
    if fid in _index_cache:
        return _index_cache[fid]
    f = BY_ID.get(fid) or BY_ID[DEFAULT]
    path, want = f[4], (f[2].lower(), f[3].lower())
    found = None
    if os.path.isfile(path):
        first = None
        for i in range(64):
            try:
                ft = ImageFont.truetype(path, 20, index=i)
            except Exception:  # noqa: BLE001 — past the last face of the collection
                break
            first = first if first is not None else i
            fam, sty = ((s or "").lower() for s in ft.getname())
            if (fam, sty) == want or (fam.replace(" ", "") == want[0].replace(" ", "") and sty == want[1]):
                found = (path, i)
                break
        if found is None and first is not None:
            found = (path, first)
    _index_cache[fid] = found
    return found


def load(fid: str, px: float) -> ImageFont.FreeTypeFont:
    px = max(1, int(round(px)))
    hit = _index(fid) or _index(DEFAULT)
    if hit:
        return ImageFont.truetype(hit[0], px, index=hit[1])
    try:
        return ImageFont.load_default(px)
    except TypeError:  # older Pillow
        return ImageFont.load_default()
