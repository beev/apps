#!/usr/bin/env python3
"""Crop a guide image that is already in place, then refresh the manifest.

Sizes may be pixels (120) or a percentage of that edge (10%). Only the edges
you name are touched.

  python3 tools/crop_image.py assets/images/guide/traffic-lights/turn-left/turning-left-at-lights.webp --top 12%
  python3 tools/crop_image.py <path> --left 100 --right 100 --bottom 5%

The width/height the page emits come from the file itself, so the manifest is
rebuilt afterwards and the pages rewritten - otherwise the old dimensions would
stay in the HTML and the layout would jump.

This edits the shipped image. Re-running strip_app_controls.py from the
original screenshot would overwrite it, so re-apply the crop if you do that.
`git checkout <path>` restores the previous version.
"""
import argparse, os, subprocess, sys
from PIL import Image

def edge(value, extent):
    if value is None: return 0
    v = value.strip()
    return round(extent * float(v[:-1]) / 100) if v.endswith('%') else int(v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    for side in ('top', 'bottom', 'left', 'right'):
        ap.add_argument(f'--{side}', help='pixels or percentage, e.g. 120 or 10%%')
    ap.add_argument('--quality', type=int, default=90)
    a = ap.parse_args()

    im = Image.open(a.path).convert('RGB')
    w, h = im.size
    t, b = edge(a.top, h), edge(a.bottom, h)
    l, r = edge(a.left, w), edge(a.right, w)
    if not (t or b or l or r):
        sys.exit("nothing to crop - name at least one of --top/--bottom/--left/--right")
    if t + b >= h or l + r >= w:
        sys.exit(f"crop removes the whole image ({w}x{h})")

    im.crop((l, t, w - r, h - b)).save(a.path, 'WEBP', quality=a.quality, method=6)
    nw, nh = Image.open(a.path).size
    print(f"{a.path}\n  {w}x{h} -> {nw}x{nh}  (displays {nw//2}x{nh//2})")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for step in ('check_images.py', 'build.py'):
        r = subprocess.run([sys.executable, f'tools/{step}'], cwd=root,
                           capture_output=True, text=True)
        print('  ' + (r.stdout.strip().splitlines() or ['ok'])[0])
        if r.returncode: sys.exit(r.stdout + r.stderr)

if __name__ == '__main__':
    main()
