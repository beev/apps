#!/usr/bin/env python3
"""Map each ![](name.png) reference in content/guide to a file in the legacy
Images tree.

The rw8 stores no image data - only the filename RapidWeaver assigned on
insert. Those names are mangled: lowercased, spaces stripped, "-2"/"-3"
appended when the media library already held that name, and "small" appended
to a downscaled copy. So a reference resolves by normalised name, and where
several folders hold that name the page's own topic breaks the tie.

Emits a TSV mapping for review. Prefers @2x originals.
"""
import os, re, csv, sys, collections

SRC = "Website Learn To Drive/Images"
SKIP_DIRS = {'Originals', 'Screenshots', 'Not used', 'Old'}

# Where the same filename lives in two folders and the page name doesn't break
# the tie. Cockpit Drill is the DSSSM lesson, so its "steering" image is the
# seating-position diagram, not the Steering page's hand-position clock face.
OVERRIDE = {
    ('controls/cockpit-drill', 'steering.png'):
        'Website Learn To Drive/Images/Controls/DSSSM/Steering.png',
}

def squash(stem):
    return re.sub(r'[\s_-]+', '', stem)

def disk_key(filename):
    """Normalised stem for a file on disk, with any @2x marker removed."""
    stem, ext = os.path.splitext(filename.lower())
    retina = '@2x' in stem
    return squash(stem.replace('@2x', '')), ext, retina

def variants(ref):
    """Candidate stems for a reference, most specific first.

    Order matters: RapidWeaver's "-2" collision suffix must come off before
    hyphens are squashed, or "gw2-2" collapses to "gw22" and then to "gw".
    """
    stem, ext = os.path.splitext(ref.lower())
    out = [squash(stem)]
    base = re.sub(r'-\d+$', '', stem)            # library-collision suffix
    if base != stem: out.append(squash(base))
    for b in list(out):
        if b.endswith('small'): out.append(b[:-5])   # RW's downscaled copy
    return out, ext

def tokens(path):
    return set(re.findall(r'[a-z]+', path.lower()))

def main():
    disk = collections.defaultdict(list)
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.lower().endswith(('.png', '.jpg', '.jpeg')): continue
            if '@4x' in f.lower(): continue          # not needed
            base, ext, retina = disk_key(f)
            disk[base].append((os.path.join(root, f), retina, ext))

    rows, unresolved = [], []
    for root, _, files in os.walk('content/guide'):
        for f in sorted(files):
            if not f.endswith('.md'): continue
            p = os.path.join(root, f)
            page = p[len('content/guide/'):-3]
            body = open(p).read()
            for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', body):
                ref = m.group(2)
                if (page, ref) in OVERRIDE:
                    plain = OVERRIDE[(page, ref)]
                    stem, ext2 = os.path.splitext(plain)
                    rows.append(dict(page=page, ref=ref, src=plain,
                                     src2x=f'{stem}@2x{ext2}' if os.path.exists(f'{stem}@2x{ext2}') else '',
                                     ambiguous='override'))
                    continue
                cands, ext = variants(ref)
                hits = []
                for c in cands:
                    if disk.get(c): hits = disk[c]; break
                if not hits:
                    unresolved.append((page, ref)); continue
                # tie-break on folder tokens shared with the page path
                pt = tokens(page)
                best = max(hits, key=lambda h: (len(tokens(os.path.dirname(h[0])) & pt), h[1]))
                folder_hits = [h for h in hits
                               if len(tokens(os.path.dirname(h[0])) & pt) == len(tokens(os.path.dirname(best[0])) & pt)]
                retina = next((h[0] for h in folder_hits if h[1]), '')
                plain  = next((h[0] for h in folder_hits if not h[1]), best[0])
                rows.append(dict(page=page, ref=ref, src=plain, src2x=retina,
                                 ambiguous='yes' if len({os.path.dirname(h[0]) for h in hits}) > 1 else ''))

    w = csv.DictWriter(open('tools/image-map.tsv', 'w'),
                       fieldnames=['page','ref','src','src2x','ambiguous'], delimiter='\t')
    w.writeheader(); w.writerows(rows)
    print(f"resolved {len(rows)}/{len(rows)+len(unresolved)} -> tools/image-map.tsv")
    print(f"  with @2x:   {sum(1 for r in rows if r['src2x'])}")
    print(f"  ambiguous:  {sum(1 for r in rows if r['ambiguous'])}")
    for p, r in unresolved: print("  UNRESOLVED", p, r)

if __name__ == '__main__':
    main()
