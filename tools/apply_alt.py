#!/usr/bin/env python3
"""Apply alt text and descriptive filenames to the guide's diagrams.

Reads tools/image-alt.tsv (page, ref, newname, alt) and for each row:
  - renames assets/images/guide/<page>/<ref-stem>.webp to <newname>.webp
  - rewrites the ![](ref) in the page's markdown to ![alt](newname.webp)

RapidWeaver's filenames (gw2-2.png, tinr1-3.png) carry no meaning and become
real URLs, so they are replaced with descriptive ones while the images are
being described anyway.

Idempotent: rows whose image is already renamed are skipped, so a partial run
can be repeated safely.
"""
import csv, os, re, sys

ROOT = 'assets/images/guide'

def main():
    rows = list(csv.DictReader(open('tools/image-alt.tsv'), delimiter='\t'))
    done = skipped = 0
    problems = []

    for r in rows:
        page, ref, new, alt = r['page'], r['ref'], r['newname'], r['alt']
        stem = os.path.splitext(ref)[0]
        old_f = os.path.join(ROOT, page, stem + '.webp')
        new_f = os.path.join(ROOT, page, new + '.webp')
        md    = os.path.join('content/guide', page + '.md')

        if not os.path.exists(md):
            problems.append(f"{page}: no markdown file"); continue
        body = open(md).read()

        if os.path.exists(new_f) and f']({new}.webp)' in body:
            skipped += 1; continue
        if not os.path.exists(old_f):
            problems.append(f"{page}/{ref}: {old_f} missing"); continue
        if f'![](%s)' % ref not in body:
            problems.append(f"{page}/{ref}: no ![]({ref}) in markdown"); continue

        os.rename(old_f, new_f)
        open(md, 'w').write(body.replace(f'![]({ref})', f'![{alt}]({new}.webp)'))
        done += 1

    print(f"applied {done}, already done {skipped}, of {len(rows)}")
    for p in problems: print("  PROBLEM", p)
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
