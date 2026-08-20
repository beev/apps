#!/usr/bin/env python3
"""Verify the built site.

Three jobs, applied to different sets of pages:

  - Markdown leftovers, on guide pages only. The guide's renderer is
    hand-written, so this is what guarantees it is total over the content: any
    construct it failed to handle shows up as unrendered markdown. These checks
    cannot run on hand-written HTML, which legitimately contains comments and
    hyphens that look like markdown to a regex.

  - Tag balance and internal link resolution, on every page. Links are resolved
    against the files on disk the way GitHub Pages resolves them, which catches
    @page-id typos, trailing-slash mistakes and references to pages that were
    renamed out from under a link.

  - URL agreement, across the whole site. Each page's canonical must be its own
    address, and the sitemap must list exactly the indexable pages - no more, no
    fewer. This is the check that keeps the site's addresses from drifting apart
    from each other, which is easy to do by hand and hard to notice.
"""
import os, re, sys
from html.parser import HTMLParser

SITE = 'https://www.neilbeaver.com'

# Where built pages live. Listed explicitly rather than walking from the root,
# which would wander into .venv and the gitignored image source folders.
ROOT_PAGES  = '.'            # hand-written pages at the top level
PAGE_TREES  = ['lessons']    # generated trees
MARKDOWN    = 'lessons/guide'  # the subset built from content/guide/*.md

VOID = {'area','base','br','col','embed','hr','img','input','link','meta',
        'param','source','track','wbr'}

# Markdown that should never survive rendering. Checked against the page body
# only, since <script> JSON legitimately contains brackets and quotes.
LEFTOVER = [
    (re.compile(r'!\['),            'unrendered image'),
    (re.compile(r'\]\('),           'unrendered link'),
    (re.compile(r'\*\*'),           'unrendered bold'),
    (re.compile(r'(?m)^\s*#{2,3} '),'unrendered heading'),
    (re.compile(r'href="@'),        'unresolved page id'),
    (re.compile(r'(?m)^\s*[-•]\s'), 'unrendered list item'),
    (re.compile(r'<!--'),           'editorial comment left in output'),
]

class Balance(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.stack=[]; self.err=[]
    def handle_starttag(self, tag, attrs):
        if tag not in VOID: self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in VOID: return
        if not self.stack: self.err.append(f'stray </{tag}>')
        elif self.stack[-1] != tag:
            self.err.append(f'</{tag}> closes <{self.stack[-1]}>')
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag: pass
        else: self.stack.pop()

def url_to_file(url):
    """Resolve a URL to a file the way GitHub Pages does."""
    path = url.split('#')[0].split('?')[0]
    if not path.startswith('/'): return None
    if path.endswith('/'):  return path.lstrip('/') + 'index.html'
    if '.' in os.path.basename(path): return path.lstrip('/')
    return path.lstrip('/') + '.html'      # flat pages: /privacy -> privacy.html

def file_to_url(path):
    """The one address a built file publishes at - its canonical form.

    A directory index is addressed with a trailing slash; a flat file is
    addressed without its .html, since Pages serves it either way and the
    extensionless form is the one this site publishes.
    """
    path = path.replace(os.sep, '/').lstrip('./')
    if os.path.basename(path) == 'index.html':
        d = os.path.dirname(path)
        return f'/{d}/' if d else '/'
    return '/' + path[:-len('.html')]

def find_pages():
    pages = []
    for f in sorted(os.listdir(ROOT_PAGES)):
        if f.endswith('.html'): pages.append(f)
    for tree in PAGE_TREES:
        for base, _, files in os.walk(tree):
            for f in sorted(files):
                if f.endswith('.html'): pages.append(os.path.join(base, f))
    return sorted(pages)

def sitemap_urls():
    if not os.path.isfile('sitemap.xml'): return None
    return set(re.findall(r'<loc>([^<]+)</loc>', open('sitemap.xml').read()))

def main():
    problems, pages = [], find_pages()

    canonicals, indexable = {}, set()
    for p in pages:
        src  = open(p).read()
        body = src.split('<body', 1)[-1]
        url  = file_to_url(p)

        if p.replace(os.sep, '/').startswith(MARKDOWN):
            body_no_ld = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.S)
            for rx, why in LEFTOVER:
                if rx.search(body_no_ld):
                    problems.append(f"{p}: {why} -> {rx.search(body_no_ld).group(0)!r}")

        b = Balance(); b.feed(src)
        for e in b.err: problems.append(f"{p}: {e}")
        if b.stack: problems.append(f"{p}: unclosed {b.stack}")

        # Commented-out markup is not a link; index.html keeps a disabled
        # screenshot block whose src has never pointed at a real file.
        live = re.sub(r'<!--.*?-->', '', src, flags=re.S)
        for m in re.finditer(r'(?:href|src)="([^"]+)"', live):
            u = m.group(1)
            if u.startswith(('http', 'mailto:', '#', 'data:')): continue
            target = url_to_file(u)
            if target and not os.path.exists(target):
                problems.append(f"{p}: broken link {u} -> {target}")
            # A link to /privacy.html resolves, but votes for an address the
            # page itself disowns in its canonical. Both work; only one counts.
            elif target and u.endswith('.html') and os.path.basename(u) != 'index.html':
                problems.append(f"{p}: link uses the .html form {u}, "
                                f"canonical is {file_to_url(target)}")

        m = re.search(r'<link rel="canonical" href="([^"]+)"', src)
        noindex = 'name="robots" content="noindex' in src
        if m:
            canonicals[p] = m.group(1)
            if m.group(1) != SITE + url:
                problems.append(f"{p}: canonical says {m.group(1)}, "
                                f"page is published at {SITE + url}")
        elif not noindex:
            problems.append(f"{p}: no canonical")
        if not noindex:
            indexable.add(SITE + url)

    listed = sitemap_urls()
    if listed is None:
        problems.append("sitemap.xml missing")
    else:
        for u in sorted(listed - indexable):
            problems.append(f"sitemap lists {u}, which is not a published address")
        for u in sorted(indexable - listed):
            problems.append(f"sitemap is missing {u}")

    print(f"checked {len(pages)} pages, {len(problems)} problems")
    for x in problems[:40]: print("  ", x)
    if len(problems) > 40: print(f"   ... and {len(problems)-40} more")
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
