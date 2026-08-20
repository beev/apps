# tools

The whole site is generated. The sources are:

    content/home.toml       the home page
    content/apps/*.toml     one file per app page
    content/pages/*.md      terms, privacy, the import guide, 404
    content/guide/*.md      the 56-page Learn To Drive guide
    content/icons.svg       the <symbol>s the module and card icons reference

Everything else at the top level — `index.html`, `lessons/`, `roads/`,
`terms.html`, `privacy.html`, `import.html`, `404.html`, `sitemap.xml` — is
build output and should not be hand-edited.

## Everyday use — no setup needed

    python3 tools/serve.py          # serve on :8000 and rebuild on every change
    python3 tools/build.py          # one-off build
    python3 tools/check_build.py    # verify the built site

`serve.py` is the one to leave running while writing: edit a source file,
refresh the browser. It applies GitHub Pages' URL rules, so `/privacy` and
`/lessons/guide` behave locally exactly as they do live. Stop it before running
`build.py` by hand, or the two builds race over the same output directory.

`check_build.py` is what makes a hand-rolled generator safe. It fails on
unrendered markdown in the guide, unbalanced HTML, links that resolve to no
file, a page whose canonical is not its own address, a sitemap that disagrees
with what was built, and output left behind by a source file that has been
deleted.

## Adding an app

Write `content/apps/<slug>.toml` — copy an existing one — and add the icon,
the two device mockups and an OG image under `assets/images/<slug>/`. The page,
the nav entry, the brand in the header and footer, the sitemap entry and its
structured data all follow from that file. An app with no `[store]` table gets
"Coming Soon" pills and no price in its structured data.

The one thing not derived is its card on the home page: those are written by
hand in `content/home.toml`, because the order and the wording are editorial.

## URLs

Addresses are written without `.html`, and with a trailing slash when the page
is a directory: `/`, `/lessons/`, `/roads/`, `/lessons/guide/`, `/privacy`,
`/terms`, `/import`. Every URL is derived from one `SITE` constant in
`build.py` and each page's own path, so a domain change is one edit rather
than a find-and-replace across the site.

`/terms`, `/privacy`, `/import` and `/lessons/guide/` are linked from inside
the shipped apps. **Those four must keep working.** `check_build.py` will not
tell you if you break them — nothing in this repo knows the apps exist — so
grep `~/neil-beaver/lessons` and `~/neil-beaver/roads` before moving a page.

`legacy_url` in the guide's front matter is the page's path on the old
RapidWeaver site. It is a record, not a redirect: those URLs were published on
a different site and have never resolved on this domain, so nothing reads the
key. Keep it for provenance.

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
