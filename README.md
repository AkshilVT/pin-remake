# Pin Remake

A layered poster editor that rebuilds Pinterest inspiration pins as live HTML/CSS/SVG compositions. Each design is made of named layers: colour blocks, photo cut-outs, live text, shapes and paper grain. You can swap, hide, reorder, move, scale and rotate each one, then save the result as a variant.

**Phase 1** rebuilds three pins:

- 01 **TOKYO**: cream and red blocks, a giant red word, a pagoda cut-out and temple roofs.
- 03 **Pagoda sketch**: paper, a stepped yellow band, a sketch layer, a wireframe and spec notes.
- 04 **Look up, kid**: six photo rays, a child cut-out and an inline headline.

Each pin also has a **Bali** variant that uses your own Bali photos.

## How it works

- The first time you open the app, `setup.py` does the following:
  - copies the pins from `~/Desktop/Pintrest-img` into `~/Fused/pin-remake/sources/`, numbered by mtime;
  - measures their colours and positions;
  - cuts the photo layers into PNGs with masks;
  - looks through `~/timepass/bali 07:26` (HEIC goes through `sips`);
  - picks the best-fitting photos and writes the 6 designs to `~/Fused/pin-remake/designs/`.
- **Left:** the pins, each followed by its original, its recreation and its variants.
- **Centre:** the canvas. Click a layer to select it, drag to move it, and use the handles to scale and rotate. Compare it with the original as an **Overlay** (opacity slider) or **Side by side**.
- **Right:** the layers. Each has an eye, a lock and drag-to-reorder, plus properties for its kind.
  - Image layers have **Swap image…**, which browses the Bali folder or any folder, or lets you pick a file. They also have fit, crop, zoom, filter, blend and opacity.
- **Buttons:** Save, Save as variant, Duplicate, Revert to original layout, and Export PNG (rendered by Python at 2×).
- Unsaved edits are kept as drafts. Every view choice lives in the URL: the design, the selected layer, the compare mode and the open swap browser. A copied link reopens the same view.

## Notes

- Fonts are the macOS system faces (Helvetica Neue Condensed Black, Futura Condensed ExtraBold, Menlo…), loaded through CSS `local()`. Nothing is fetched at runtime.
- Cut-outs use colour and saturation masks, which suit these pins' flat backgrounds. Swapped photos use sky removal. rembg/OpenCV are not needed.
- To add more pins (02, 05–11), write more designs in the same JSON format. The format is in `SKILL.md`.
