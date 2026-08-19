#!/usr/bin/env python3
"""One-off migration: RapidWeaver 8 document -> committed Markdown content files.

Run once. The rw8 source is gitignored, so the build must never depend on it:
this script's OUTPUT (content/lessons/**.md) is the version-controlled source
of truth from here on. Kept only so the conversion is reproducible/auditable.

Heading levels are remapped deliberately. The old Navigator theme owned h1-h3
for its banner, so pages started at h4. Here the page title becomes the h1
(emitted by the template from front matter) and h5 sections become h2.

ALREADY RUN. content/guide/ is now hand-edited and is the source of truth;
re-running would destroy that work, so this script refuses to overwrite a
populated content/guide/. Pass --force only to redo the migration from scratch,
and only against a clean git tree you can recover from.
"""
import os, re, sys, plistlib, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rw_extract import extract

# Advert page; dropped on the author's instruction. Home is superseded by the
# existing site homepage.
SKIP_PAGES = {'Car Insurance', 'Home'}

MERGED = {}

# The old site's topics were named after the manoeuvre; the app groups them by
# road feature. These overrides bring the site into line with the app, so a
# lesson in Lessons and its page here carry the same name.
#   {old PageTitle: (new title, new slug, new parent slug or None)}
RETITLE = {
    'Give Way Junctions': ('Junctions',      'junctions', None),
    'Emergency Stop':     ('Stopping',       'stopping',  None),
}

# Pages whose body is appended to another page instead of standing alone.
# Stop Junctions was a topic of its own; give way and stop are now both
# explained on the single Junctions topic page.
#   {old PageTitle: (target path, heading to introduce the merged body)}
MERGE_INTO = {
    'Stop Junctions': ('junctions', 'Stop junctions'),
}

def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s.lower())).strip('-')

def page_meta(d):
    c = plistlib.load(open(os.path.join(d, 'Contents.plist'), 'rb'))
    return c['SandwichFillings'][0]['Dictionary']

def legacy_root(meta):
    """The old RapidWeaver SiteRoot, e.g. "controls/cockpitdrill". Recorded in
    front matter so the old published URLs stay traceable; new paths are
    hyphenated slugs derived from the page title instead."""
    for m in meta.get('PublishingManifests', {}).values():
        if 'SiteRoot' in m:
            return m['SiteRoot']
    return None

def md_escape(t):
    # Body text is plain prose; only markdown-active leading chars need care.
    return re.sub(r'^([#>\-*+]|\d+\.)', r'\\\1', t)

def to_markdown(runs):
    """Runs -> markdown blocks. Drops the leading h4 (it becomes front-matter
    title) and the trailing App Store badge markup."""
    out, title = [], None
    for r in runs:
        if r['image']:
            out.append(f"\n\n![]({r['image']})\n\n"); continue
        t = r['text']
        if not t.strip() and '\n' not in t:
            continue
        if r['tag'] == 'h4' and title is None:
            title = t.strip(); continue
        if r['tag'] in ('h4', 'h5'):
            out.append(f"\n\n## {t.strip()}\n\n"); continue
        if r['italic'] and t.strip():
            out.append(f"*{t.strip()}*"); continue
        out.append(t)
    body = ''.join(out)
    # Strip the dead linkmaker.itunes.apple.com badges (all 54 of them) and any
    # other author-typed raw HTML, flagging what was removed.
    removed = re.findall(r'<(?:a|iframe|img)\b[^>]*>', body)
    body = re.sub(r'<a\b[^>]*>.*?</a>', '', body, flags=re.S)
    body = re.sub(r'<iframe\b[^>]*>.*?</iframe>', '', body, flags=re.S)
    body = re.sub(r'</?(?:p|br|small)\s*/?>', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body).strip()
    return title, body, removed

def walk(pages_dir, parent=None, out=None, order=0):
    out = out if out is not None else []
    entries = sorted(d for d in os.listdir(pages_dir)
                     if os.path.isdir(os.path.join(pages_dir, d)))
    for i, name in enumerate(entries, 1):
        d = os.path.join(pages_dir, name)
        if not os.path.exists(os.path.join(d, 'Contents.plist')):
            continue
        meta = page_meta(d)
        title = meta['PageTitle']
        legacy = legacy_root(meta)
        if title in MERGE_INTO:
            target, heading = MERGE_INTO[title]
            _, body, removed = to_markdown(extract(os.path.join(d, 'Data.archive')))
            MERGED.setdefault(target, []).append((heading, body))
            continue
        if title in RETITLE:
            title, leaf, forced_parent = RETITLE[title]
            parent_for_path = forced_parent
        else:
            leaf = slug(title)
            parent_for_path = parent
        root = f'{parent_for_path}/{leaf}' if parent_for_path else leaf
        if title not in SKIP_PAGES and os.path.exists(os.path.join(d, 'Data.archive')):
            t, body, removed = to_markdown(extract(os.path.join(d, 'Data.archive')))
            out.append(dict(title=title, path=root, parent=parent_for_path, order=i,
                            body=body, removed=removed, legacy=legacy,
                            date=str(meta.get('CreatedDate', ''))[:10]))
        child = os.path.join(d, 'ChildPages')
        if os.path.isdir(child):
            walk(child, parent=(root if title not in SKIP_PAGES else None), out=out)
    return out

def renumber(pages):
    """Sibling order is inherited from the rw8 tree, so a page moved by RETITLE
    keeps its old index (Stop was topic 8, now child 5 of Junctions). Renumber
    each sibling group 1..n, preserving relative order."""
    groups = {}
    for p in pages:
        groups.setdefault(p['parent'], []).append(p)
    for sibs in groups.values():
        for i, p in enumerate(sorted(sibs, key=lambda x: x['order']), 1):
            p['order'] = i
    return pages

def main(rw8):
    pages = renumber(walk(os.path.join(rw8, 'Pages')))
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'content', 'guide')
    flagged = []
    for p in pages:
        for heading, extra in MERGED.get(p['path'], []):
            p['body'] = f"{p['body']}\n\n## {heading}\n\n{extra}"
        dest = os.path.join(root, p['path'] + '.md')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        fm = [f"title: {p['title']}", f"path: {p['path']}", f"order: {p['order']}"]
        if p['parent']: fm.append(f"parent: {p['parent']}")
        if p['date']:   fm.append(f"lastmod: {p['date']}")
        if p['legacy']: fm.append(f"legacy_url: {p['legacy']}")
        with open(dest, 'w') as f:
            f.write('---\n' + '\n'.join(fm) + '\n---\n\n' + p['body'] + '\n')
        if p['removed']:
            flagged.append((p['path'], p['removed']))
    print(f"wrote {len(pages)} pages to content/guide/")
    tags = {}
    for path, rem in flagged:
        for r in rem:
            tags.setdefault(re.match(r'<(\w+)', r).group(1), []).append(path)
    print("\nstripped inline HTML (review these):")
    for t, ps in tags.items():
        print(f"  <{t}> removed from {len(ps)} pages" + (f": {', '.join(ps)}" if len(ps) <= 3 else ""))

if __name__ == '__main__':
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(repo, 'content', 'guide')
    if os.path.isdir(out) and os.listdir(out) and '--force' not in sys.argv:
        sys.exit(f"refusing to overwrite {out} (already migrated and hand-edited).\n"
                 f"Re-run with --force only against a clean git tree.")
    main(sys.argv[1])
