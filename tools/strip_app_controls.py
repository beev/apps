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
GREEN_TOL = 24    # how far from the verge colour still counts as verge

# Disabled toggles are drawn washed out, close enough to the verge that a
# loose tolerance swallowed their edges - the component came out narrower than
# the control and filling its box left faint arcs behind on the grass.

# Letters in a word sit only a few pixels apart, so testing each glyph on its
# own fails: the ring drawn around one letter lands on the next one and the
# component looks like it is touching something. Dilating first merges each
# label into a single component, which is also a tidier thing to fill.

def crop_device_chrome(a):
    """Trim the status/navigation bar and the home indicator from a full-device
    screenshot, leaving just the app's drawing.

    Both bands are flat: the bars are a neutral grey and the home indicator is
    pure black, each spanning the full width. Guarded so an already-cropped
    screenshot is left alone - the guards fail unless a genuine chrome band is
    present at the very top or bottom.
    """
    h, w, _ = a.shape
    y0, y1 = 0, h

    chrome = a[2, w // 2]
    neutral = int(chrome.max() - chrome.min()) < 8
    frac = lambda row, c: float((np.abs(a[row] - c).sum(axis=1) < 24).mean())
    if neutral and frac(2, chrome) > 0.8:
        while y0 < h and frac(y0, chrome) > 0.5:
            y0 += 1

    dark = lambda row: float((a[row].max(axis=1) < 20).mean())
    if dark(h - 1) > 0.9:
        while y1 > y0 and dark(y1 - 1) > 0.9:
            y1 -= 1

    return a[y0:y1], (y0, h - y1)

def is_traffic_light(w, h, size, sat):
    """Size alone separates them, with a wide margin.

    Signals run 24,000-30,000 pixels; the largest control - a toggle - is
    about 6,700, and a button around 6,300. An earlier version also required
    the shape to be taller than wide, which deleted the L-shaped filter
    signals: a main head with a filter head beside it is 182x221, a ratio of
    1.21. Lamp colour is no good either, since a signal showing nothing lit
    has no saturated pixels at all.
    """
    return size > 12000

def strip(path, out_dir):
    im = Image.open(path).convert('RGB')
    a = np.asarray(im).astype(int)
    a, (cut_top, cut_bottom) = crop_device_chrome(a)
    h, w, _ = a.shape

    cols, counts = np.unique(a.reshape(-1, 3), axis=0, return_counts=True)
    greenish = (cols[:, 1] > 100) & (cols[:, 1] > cols[:, 0] * 1.6) & (cols[:, 1] > cols[:, 2] * 1.6)
    g = cols[greenish][np.argmax(counts[greenish])]
    green = (np.abs(a - g).sum(axis=2) < GREEN_TOL)

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
    crop = f", cropped {cut_top}px top / {cut_bottom}px bottom" if (cut_top or cut_bottom) else ""
    print(f"{os.path.basename(path)[:34]:34} removed {removed:3} controls, "
          f"kept {kept} light(s), {changed*100:.2f}% repainted{crop}")
    return dest

if __name__ == '__main__':
    for p in sys.argv[2:]:
        strip(p, sys.argv[1])
