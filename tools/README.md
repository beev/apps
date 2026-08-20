# tools

The site is generated. `content/guide/*.md` is the source; everything under
`lessons/guide/` is built output and should not be hand-edited.

## Everyday use — no setup needed

    python3 tools/serve.py          # serve on :8000 and rebuild on every change
    python3 tools/build.py          # one-off build
    python3 tools/check_build.py    # verify the built HTML

`serve.py` is the one to leave running while writing: edit a `.md`, refresh the
browser.

## Image tools — need the virtualenv

These use Pillow, numpy and scipy, so they run under `.venv` (gitignored):

    python3 -m venv .venv && .venv/bin/pip install Pillow numpy scipy

Then:

    # remove the app's UI from screenshots, and crop device chrome
    .venv/bin/python tools/strip_app_controls.py OUTDIR "Website New Images"/*.png

    # crop an image that is already in place; sizes are pixels or percentages
    .venv/bin/python tools/crop_image.py path/to/image.webp --top 12% --bottom 80

    # verify every image reference resolves, and rebuild the size manifest
    python3 tools/check_images.py

`crop_image.py` edits the shipped image and then rebuilds, so the width and
height in the HTML follow. `git checkout <path>` undoes a crop.

## One-off

`migrate.py` converted the old RapidWeaver document and refuses to run again.
`rw_extract.py` and `resolve_images.py` support it and are kept for reference.
