---
name: pin-remake
description: Layered poster editor. Rebuilds Pinterest pins as editable layer designs (JSON), swaps layer photos, sketches or cuts out photos, exports PNGs.
approve: [setup.py, designs.py]
---
# Pin Remake

All data lives in `~/Fused/pin-remake/`. The page and these files share it:

- `sources/NN.jpg` are copies of the Pinterest pins, numbered by mtime (01 = oldest). `sources/index.json` lists them.
- `designs/<slug>.json` are the saved designs. `drafts/<slug>.json` hold unsaved edits made in the page.
- `originals/<slug>.json` are the shipped layouts that "Revert" restores.
- `layers/NN/*.png` are photo layers cut from the pins, each with a `*-mask.png`.
- `cutouts/` holds cut-outs and sketches. `photos/` holds browser-ready copies of photos. `exports/` holds PNGs.

The shipped designs are `01-tokyo`, `03-pagoda-sketch` and `04-look-up-kid`, plus a `-bali` variant of each.

## Design JSON format

```json
{
  "version": 1, "slug": "01-tokyo", "name": "TOKYO — recreation", "pin": "01", "variant_of": null,
  "source": "~/Fused/pin-remake/sources/01.jpg (absolute)", "source_original": "~/Desktop/Pintrest-img/<hash>.jpg",
  "canvas": {"width": 735, "height": 919, "aspect": "4:5", "background": "#e9e4da"},
  "layers": [ ... ], "notes": "", "created": "ISO", "updated": "ISO"
}
```

**Layers** are drawn in ascending `z` order. Every layer has these fields:

- `id`, `name`, `kind` (`image` | `text` | `rect` | `polygon` | `svg`), `visible`, `locked`
- `x`, `y`, `w`, `h`: the box, in % of the canvas width (x, w) and height (y, h)
- `rotation` in degrees, clockwise about the box centre
- `z`, `opacity` (0–1), `blend` (`normal` | `multiply` | `screen` | `overlay` | `darken` | `lighten` | `difference`)

Fields by kind:

- **image**
  - `src`: an absolute PNG or JPEG path.
  - `mask`: an optional PNG whose alpha is stretched over the box. Swapped photos keep this shape.
  - `fit`: `fill` | `cover` | `contain`.
  - `crop`: `{x, y, scale}`. x and y are the focus point in % (CSS object-position), and scale zooms about that point.
  - `filter`: `none` | `bw` | `contrast` | `sketch`. With `sketch`, `src` is already a sketch PNG.
  - `contrast`, `brightness`: multipliers.
  - `swap`: how a new photo is applied. `mask` keeps the shape, `cutout` removes the sky, `sketch` makes a sketch, `free` uses no mask.
  - `src_orig`, `mask_orig`, `src_raw`: the layer's original image, its original mask, and the photo before the sketch filter.
- **text**
  - `text` (use `\n` for line breaks), `font` (a font id, listed below), `color`.
  - `size` in % of the canvas height. It is ignored when `fit` is `stretch`.
  - `weight`: a fallback only. The font id fixes the face.
  - `tracking` in 1/1000 em, `line_height` (a multiplier), `align` (`left` | `center` | `right`).
  - `fit`: `none`, or `stretch`, which maps the ink bounds onto the box.
  - `effect`: `none` | `inline`. `effect_color` sets the colour of the inline stroke.
  - Line i has its baseline at `(i*line_height + line_height/2 + 0.35) * size` below the box top.
- **rect**: `color`.
- **polygon**: `color`, and `points` as `[[x, y], …]` in % of the box.
- **svg**: `color`, plus either `preset: "grain"` (paper grain) or `svg` (inner markup) with `viewbox`. The default viewbox is `"0 0 100 100"`, stretched to the box. The exporter draws only line, circle, ellipse, rect, polyline and polygon elements.

**Font ids**: `hn-cond-black`, `hn-cond-bold`, `hn-bold`, `hn-medium`, `hn-light`, `impact`, `din-cond`, `avenir-cond-heavy`, `futura-bold`, `futura-cond-xb`, `rockwell-bold`, `courier`, `menlo`. These are macOS system fonts. Each is loaded in the page through CSS `local()` and in the exporter through PIL.

**Editing as a bot**: write `designs/<slug>.json` directly, or use `designs.py`. A draft in `drafts/<slug>.json` takes precedence in the page, so delete it or call `designs.py` with `action: "save"` after editing.

## setup.py
First-run build. It copies the pins into `sources/`, cuts pins 01, 03 and 04 into layers, indexes the Bali folder, picks Bali photos, and writes the 6 designs. Writes everything under ~/Fused/pin-remake/. It overwrites the shipped designs only when `force` is true.
- Args:
  - `force` (bool, default false): rebuild everything and overwrite the 6 shipped designs.
  - `rebuild` (str, default ""): a comma list of steps to redo. Steps: `sources`, `pin01`, `pin03`, `pin04`, `bali_index`, `bali_build`.
- Returns `{"status": "running"|"done"|"error", "step": str, "message": str, "progress": float}`. While the status is `"running"`, call again. When done, the result also carries `"steps": {step: result}`.
- Example: `{"action":"py","app":"pin-remake","file":"setup.py","args":{}}`

## designs.py
Lists, reads and writes designs. `list` and `get` write nothing. `save`, `draft`, `save_as`, `duplicate`, `revert`, `discard` and `delete` write `designs/` or `drafts/`.
- Args:
  - `action` (str, default "list"): `list` | `get` | `save` | `draft` | `discard` | `save_as` | `duplicate` | `revert` | `delete`.
  - `slug` (str): required for every action except `list`.
  - `design` (str, JSON, default ""): the full design for `save`, `draft`, `save_as` and `duplicate`. When empty, the current draft or saved copy is used.
  - `name` (str, default ""): the new name for `save_as` and `duplicate`.
- Returns:
  - `list`: `{"root", "pins": [{n, file, original, name, w, h, title}], "designs": [{slug, name, pin, variant_of, has_draft, shipped, design}], "fonts": [...], "bali_dir", "built"}`
  - `get`: `{"design": {...}, "has_draft": bool}`
  - `save_as` and `duplicate`: `{"ok": true, "slug": new_slug, "design": {...}}`
  - `revert`: writes the shipped layout as a draft and returns `{"ok": true, "design": {...}, "has_draft": true}`
  - `delete`: removes only designs the user made.
- Example: `{"action":"py","app":"pin-remake","file":"designs.py","args":{"action":"get","slug":"01-tokyo-bali"}}`

## list_folder.py
Lists and thumbnails a photo folder, sorted by date taken (EXIF, Spotlight or mtime). HEIC is supported. Writes only thumbnail cache files in `cache/`.
- Args:
  - `path` (str, default: the Bali folder `~/timepass/bali 07:26`)
  - `offset` (int, default 0)
  - `count` (int, default 60, max 200)
  - `size` (int, default 320): the long side of each thumbnail, in px.
- Returns `{"status": "ok"|"indexing", "folder", "total", "offset", "next_offset": int|null, "photos": [{path, name, n, date, place, w, h, thumb}]}`.
  - `n` is the 1-based position in date order, and `thumb` is a JPEG path.
  - On a big folder's first scan, the status is `"indexing"` with no photos. Call again until it is `"ok"`.
- Example: `{"action":"py","app":"pin-remake","file":"list_folder.py","args":{"path":"~/timepass/bali 07:26","count":20}}`

## cutout.py
Cuts a subject or region out of a photo into a transparent PNG and its mask. Writes `cutouts/<name>-<hash>.png` and `-mask.png`.
- Args:
  - `src` (str, required)
  - `mode` (str, default "auto"):
    - `auto` / `sky`: removes the sky connected to the top edge, falling back to `vignette`.
    - `polygon`: cuts along `polygon`.
    - `rect`: keeps the whole region.
    - `vignette`: soft edges.
  - `x`, `y`, `w`, `h` (float, default 0, 0, 100, 100): the region to crop first, in % of the photo.
  - `polygon` (str, JSON `[[x, y], …]` in % of the region, default "")
  - `bw` (bool, default false): high-contrast black and white.
- Returns `{"png": str, "mask": str, "width": int, "height": int, "mode": str}`
- Example: `{"action":"py","app":"pin-remake","file":"cutout.py","args":{"src":"~/timepass/bali 07:26/IMG_1234.jpg","mode":"auto","bw":true}}`

## sketch.py
Turns a photo into a pencil/ink sketch: dark ink on transparent with faded edges, for multiply-style layers like pin 03's temple. Writes `cutouts/<name>-sketch-<hash>.png` and a browser copy of the photo in `photos/`.
- Args:
  - `src` (str, required)
  - `strength` (float, default 1.0, range 0.2–3)
  - `fade` (float, default 0.18, range 0–0.5): the edge fade as a share of the size.
- Returns `{"png": str, "width": int, "height": int, "raw": str}`. `raw` is the browser-ready photo.
- Example: `{"action":"py","app":"pin-remake","file":"sketch.py","args":{"src":"~/timepass/bali 07:26/IMG_1234.jpg","strength":1.2}}`

## prepare_photo.py
Makes a browser-ready JPEG copy of any photo (HEIC → JPEG, long side ≤ `max_side`). Use it before putting a photo into an image layer's `src`. Writes `photos/`.
- Args: `src` (str, required), `max_side` (int, default 2400)
- Returns `{"path": str, "width": int, "height": int}`
- Example: `{"action":"py","app":"pin-remake","file":"prepare_photo.py","args":{"src":"~/timepass/bali 07:26/IMG_0005.HEIC"}}`

## export_png.py
Renders a design to a full-resolution PNG, from its draft when one exists. Writes `exports/<slug>.png`, or `<slug>@<scale>x.png` when `scale` is not 1.
- Args:
  - `slug` (str, required)
  - `scale` (float, default 1.0, range 0.25–4): multiplies the canvas size.
  - `draft` (bool, default true): use the unsaved draft if there is one.
- Returns `{"png": str, "width": int, "height": int, "seconds": float}`
- Example: `{"action":"py","app":"pin-remake","file":"export_png.py","args":{"slug":"04-look-up-kid-bali","scale":2}}`

## import_file.py
Stores an image sent as base64 (the page's "Pick a file…") so layers can use it. Writes `uploads/` and `photos/`.
- Args: `name` (str, required, with extension), `data` (str, required, base64 or a data URL, ≤ 60 MB)
- Returns `{"path": str, "web": str, "bytes": int}`
- Example: `{"action":"py","app":"pin-remake","file":"import_file.py","args":{"name":"sky.jpg","data":"data:image/jpeg;base64,/9j/4AAQ..."}}`
