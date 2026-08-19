#!/usr/bin/env python3
"""Convert the legacy diagrams to WebP under assets/images/guide/.

Sources are the @2x originals from the gitignored RapidWeaver image tree, as
mapped in tools/image-map.tsv. Only the WebP output is committed - the PNGs
stay out of git, where they would live in history permanently.

Output is one file per image at the @2x pixel size, in a per-page directory
because the legacy filenames (steering.png, crossroads.png) collide across
topics. Pages display them at half size via width/height, so every screen gets
a sharp diagram without the complexity of srcset.

Records real pixel dimensions in tools/image-manifest.tsv for the page builder
to emit as width/height, which is what stops layout shift.
"""
import csv, os, subprocess, struct, sys

OUT_ROOT = 'assets/images/guide'
QUALITY  = '90'          # flat-colour line art; artefacts show up early here

def dims(path):
    with open(path, 'rb') as f: head = f.read(32)
    if head[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', head[16:24])
    out = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', path],
                         capture_output=True, text=True).stdout
    w = h = 0
    for line in out.splitlines():
        if 'pixelWidth' in line:  w = int(line.split(':')[1])
        if 'pixelHeight' in line: h = int(line.split(':')[1])
    return w, h

def main():
    rows = list(csv.DictReader(open('tools/image-map.tsv'), delimiter='\t'))
    manifest, total_in, total_out, failed = [], 0, 0, []

    for r in rows:
        src = r['src2x'] or r['src']
        if not os.path.exists(src):
            failed.append((r['page'], r['ref'], 'source missing')); continue

        stem = os.path.splitext(r['ref'])[0]
        dest = os.path.join(OUT_ROOT, r['page'], stem + '.webp')
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        p = subprocess.run(['cwebp', '-q', QUALITY, '-mt', src, '-o', dest],
                           capture_output=True, text=True)
        if p.returncode != 0 or not os.path.exists(dest):
            failed.append((r['page'], r['ref'], p.stderr.strip()[:80])); continue

        w, h = dims(src)
        total_in  += os.path.getsize(src)
        total_out += os.path.getsize(dest)
        manifest.append(dict(page=r['page'], ref=r['ref'],
                             file=os.path.relpath(dest, 'assets/images/guide'),
                             w=w, h=h,                      # intrinsic (@2x)
                             dw=round(w / 2), dh=round(h / 2)))  # display size

    with open('tools/image-manifest.tsv', 'w') as f:
        w_ = csv.DictWriter(f, fieldnames=['page','ref','file','w','h','dw','dh'],
                            delimiter='\t')
        w_.writeheader(); w_.writerows(manifest)

    print(f"converted {len(manifest)}/{len(rows)}")
    print(f"  {total_in/1024/1024:.2f} MB -> {total_out/1024/1024:.2f} MB "
          f"({100 - 100*total_out/total_in:.0f}% smaller)")
    for page, ref, why in failed: print(f"  FAILED {page} {ref}: {why}")
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
