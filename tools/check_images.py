#!/usr/bin/env python3
"""Verify every image reference in the guide resolves, and rebuild the
width/height manifest the page builder needs to emit layout-shift-free markup.

Run after renaming images. Dimensions are read back from the WebP files
themselves rather than carried over from the sources, so the manifest always
describes what actually ships.
"""
import os, re, csv, subprocess, sys

ROOT = 'assets/images/guide'

def webp_dims(path):
    out = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', path],
                         capture_output=True, text=True).stdout
    w = h = 0
    for line in out.splitlines():
        if 'pixelWidth' in line:  w = int(line.split(':')[1])
        if 'pixelHeight' in line: h = int(line.split(':')[1])
    return w, h

rows, missing, no_alt = [], [], []
used = set()
for root, _, files in os.walk('content/guide'):
    for f in sorted(files):
        if not f.endswith('.md'): continue
        p = os.path.join(root, f)
        page = p[len('content/guide/'):-3]
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', open(p).read()):
            alt, ref = m.group(1), m.group(2)
            img = os.path.join(ROOT, page, ref)
            if not alt.strip(): no_alt.append(f"{page} {ref}")
            if not os.path.exists(img):
                missing.append(f"{page} -> {img}"); continue
            used.add(os.path.normpath(img))
            w, h = webp_dims(img)
            rows.append(dict(page=page, file=os.path.relpath(img, ROOT),
                             w=w, h=h, dw=round(w/2), dh=round(h/2), alt=alt))

orphans = []
for root, _, files in os.walk(ROOT):
    for f in files:
        if f.endswith('.webp') and os.path.normpath(os.path.join(root, f)) not in used:
            orphans.append(os.path.join(root, f))

with open('tools/image-manifest.tsv', 'w') as fh:
    w_ = csv.DictWriter(fh, fieldnames=['page','file','w','h','dw','dh','alt'], delimiter='\t')
    w_.writeheader(); w_.writerows(rows)

print(f"{len(rows)} references, all resolving" if not missing else f"{len(rows)} ok, {len(missing)} MISSING")
for x in missing: print("  MISSING", x)
for x in no_alt:  print("  NO ALT ", x)
for x in orphans: print("  ORPHAN ", x)
sys.exit(1 if (missing or no_alt or orphans) else 0)
