#!/usr/bin/env python3
"""Remove the app's UI controls from a Lessons screenshot.

The controls - toggles, buttons and their text labels - are drawn on the flat
green verge, so they appear as non-green components fully enclosed by green.
Traffic lights sit on that same green, so they are identified and kept: they
are tall, large, and contain a saturated lamp, none of which is true of a
toggle or a button.

Each removed component is filled to its bounding box rather than its exact
pixels, which takes the anti-aliased edge with it and leaves flat green.

Usage: strip_app_controls.py out_dir image [image ...]
"""
import os, sys
import numpy as np
from PIL import Image
from scipy import ndimage

MIN_PX  = 120     # smaller than the smallest glyph
PAD     = 3       # eat the anti-aliased fringe
MERGE   = 5       # dilation that joins neighbouring letters into one word

# Letters in a word sit only a few pixels apart, so testing each glyph on its
# own fails: the ring drawn around one letter lands on the next one and the
# component looks like it is touching something. Dilating first merges each
# label into a single component, which is also a tidier thing to fill.

def is_traffic_light(w, h, size, sat):
    return size > 15000 and h > 1.5 * w and sat > 0.08

def strip(path, out_dir):
    im = Image.open(path).convert('RGB')
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape

    cols, counts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    greenish = (cols[:, 1] > 100) & (cols[:, 1] > cols[:, 0] * 1.6) & (cols[:, 1] > cols[:, 2] * 1.6)
    g = cols[greenish][np.argmax(counts[greenish])]
    green = (np.abs(a - g).sum(axis=2) < 40)

    merged = ndimage.binary_dilation(~green, np.ones((MERGE, MERGE), bool))
    lab, n = ndimage.label(merged)
    out = a.copy()
    removed = kept = 0
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = sl
        y0, y1, x0, x1 = ys.start, ys.stop, xs.start, xs.stop
        comp = (lab[sl] == i) & ~green[sl]      # dilation only groups; measure real pixels
        size = int(comp.sum())
        if size < MIN_PX: continue

        p = 3
        ry0, ry1 = max(0, y0-p), min(h, y1+p)
        rx0, rx1 = max(0, x0-p), min(w, x1+p)
        ring = green[ry0:ry1, rx0:rx1].copy()
        ring[y0-ry0:y0-ry0+(y1-y0), x0-rx0:x0-rx0+(x1-x0)] = True
        # The road's bounding box covers almost the whole image, so its ring is
        # nearly all interior - which counts as green - and it passes the test.
        # Size is what separates it from a control: reject anything occupying a
        # large share of the frame. This also lets a control clipped by the edge
        # of the screenshot through, which the earlier edge test rejected.
        if (y1-y0) * (x1-x0) > 0.15 * w * h: continue
        if ring.mean() <= 0.97: continue

        px = a[sl][comp]
        mx, mn = px.max(axis=1), px.min(axis=1)
        sat = float((((mx - mn) > 90) & (mx > 140)).mean())

        if is_traffic_light(x1-x0, y1-y0, size, sat):
            kept += 1
            continue
        out[max(0,y0-PAD):min(h,y1+PAD), max(0,x0-PAD):min(w,x1+PAD)] = g
        removed += 1

    # Guard against a rule change quietly flattening the whole picture: an
    # earlier version filled entire images green because the road passed the
    # enclosure test. Controls are a small share of any screenshot.
    changed = float((np.abs(a - out).sum(axis=2) > 10).mean())
    if changed > 0.10:
        raise SystemExit(f"ABORT {os.path.basename(path)}: would repaint "
                         f"{changed*100:.1f}% of the image - that is not just controls")

    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, os.path.basename(path))
    Image.fromarray(out.astype(np.uint8)).save(dest)
    print(f"{os.path.basename(path):16} removed {removed:3} controls, "
          f"kept {kept} traffic light(s), {changed*100:.2f}% of pixels repainted")
    return dest

if __name__ == '__main__':
    for p in sys.argv[2:]:
        strip(p, sys.argv[1])
