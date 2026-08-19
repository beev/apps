#!/usr/bin/env python3
"""Build the guide's HTML from content/guide/*.md.

Everything shared - head, header, sidebar, breadcrumbs, footer - lives here
once, so a change to the footer is one edit rather than fifty. Page URLs come
from the front matter rather than being baked into the files, so moving a page
is a front-matter edit plus a rebuild.

Markdown support is deliberately narrow: exactly the constructs the content
uses (h2, h3, paragraphs, images, links, bold, italic, ordered and unordered
lists). tools/check_build.py fails the build if anything unhandled reaches the
output, which is what makes a hand-rolled renderer safe here.

Usage: python3 tools/build.py
"""
import os, re, csv, html, shutil, sys
from datetime import date

SITE      = 'https://www.neilbeaver.com'

# Maps Embed API key. Public by necessity - browser APIs expose their key in
# page source - so it is restricted in the Cloud console to this site's
# referrers and to the Maps Embed API alone, which is free and unmetered.
# It is deliberately NOT the key the Roads app uses.
MAPS_API_KEY = 'AIzaSyCl0ieLxi9ZgkI555zxSXkqKOmoey-mrDQ'
GUIDE_URL = '/lessons/guide'
OUT       = 'lessons/guide'
SRC       = 'content/guide'
IMG_URL   = '/assets/images/guide'

# Pages outside the guide that must stay in the sitemap. Their lastmod values
# are kept as they are so a guide rebuild does not churn every entry.
STATIC_URLS = [
    ('/',             '2026-08-04', 'weekly',  '1.0'),
    ('/import.html',  '2026-08-04', 'monthly', '0.7'),
    ('/terms.html',   '2026-08-04', 'yearly',  '0.3'),
    ('/privacy.html', '2026-08-04', 'yearly',  '0.3'),
]

# ---------------------------------------------------------------- content ---

def load_pages():
    pages = {}
    for root, _, files in os.walk(SRC):
        for f in sorted(files):
            if not f.endswith('.md'): continue
            raw = open(os.path.join(root, f)).read()
            _, fm, body = raw.split('---\n', 2)
            meta = dict(re.findall(r'^(\w+): (.*)$', fm, re.M))
            meta['body']  = body.strip()
            meta['draft'] = meta.get('draft') == 'true'
            meta['order'] = int(meta.get('order', 0))
            pages[meta['path']] = meta
    for p in pages.values():
        p['url'] = f"{GUIDE_URL}/" if p['path'] == 'index' else f"{GUIDE_URL}/{p['path']}/"
    return pages

def tree(pages):
    tops = sorted((p for p in pages.values()
                   if 'parent' not in p and p['path'] != 'index'),
                  key=lambda p: p['order'])
    for t in tops:
        t['children'] = sorted((p for p in pages.values()
                                if p.get('parent') == t['path']),
                               key=lambda p: p['order'])
    return tops

# --------------------------------------------------------------- markdown ---

INLINE = re.compile(
    r'!\[([^\]]*)\]\(([^)]+)\)'      # 1,2 image
    r'|\[([^\]]+)\]\(([^)]+)\)'      # 3,4 link
    r'|\*\*([^*]+)\*\*'              # 5   bold
    r'|\*([^*]+)\*'                  # 6   italic
)

class BuildError(Exception): pass

def resolve(href, pages, where):
    """@page-id becomes a real URL; anything else passes through untouched."""
    if not href.startswith('@'):
        return href
    target = href[1:]
    if target not in pages:
        raise BuildError(f"{where}: link to unknown page '@{target}'")
    return pages[target]['url']

def inline(text, pages, where, page_path):
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        pos = m.end()
        if m.group(1) is not None:                       # image
            out.append(img_tag(m.group(1), m.group(2), page_path))
        elif m.group(3) is not None:                     # link
            url = resolve(m.group(4), pages, where)
            out.append(f'<a href="{html.escape(url, quote=True)}">'
                       f'{html.escape(m.group(3))}</a>')
        elif m.group(5) is not None:                     # bold may wrap a link
            out.append(f'<strong>{inline(m.group(5), pages, where, page_path)}</strong>')
        else:
            out.append(f'<em>{inline(m.group(6), pages, where, page_path)}</em>')
    out.append(html.escape(text[pos:]))
    return ''.join(out)

DIMS = {}
def img_tag(alt, src, page_path):
    key = (page_path, src)
    d = DIMS.get(key)
    url = f'{IMG_URL}/{page_path}/{src}'
    attrs = (f'src="{html.escape(url, quote=True)}" '
             f'alt="{html.escape(alt, quote=True)}"')
    if d:
        attrs += f' width="{d["dw"]}" height="{d["dh"]}"'
    return f'<figure class="guide-figure"><img {attrs} loading="lazy" decoding="async"></figure>'

LIST_RE = re.compile(r'^(?:([-•])|(\d+)\.)\s+(.*)$')
MAP_RE  = re.compile(r'^@map\[([^\]]*)\]\(([^)]+)\)$')

def map_embed(title, url):
    """A Google Maps embed behind a click-to-load button.

    Nothing contacts Google until the reader presses the button, so no cookie
    is set unless they ask for the map - which keeps three maps on one page
    from putting a consent banner on all 56. The button is labelled with what
    it does and sits next to the notice, so pressing it is the consent.

    These are the keyless share-embed URLs (maps/embed?pb=...), so no API key
    is involved. Coordinates and zoom are read back out of the pb string for
    the no-JavaScript fallback link rather than being stored twice.
    """
    # Two forms are accepted. "satellite:lat,lng,zoom" builds a Maps Embed API
    # URL, whose maptype=satellite may drop the road-name labels the keyless
    # share embed always shows. Anything else must be a keyless share-embed
    # URL, which needs no key at all.
    m = re.fullmatch(r'satellite:(-?[\d.]+),(-?[\d.]+),(\d+)', url)
    if m:
        lat, lng, zoom = m.group(1), m.group(2), m.group(3)
        url = (f'https://www.google.com/maps/embed/v1/view?key={MAPS_API_KEY}'
               f'&center={lat},{lng}&zoom={zoom}&maptype=satellite')
    else:
        if not url.startswith('https://www.google.com/maps/embed?pb='):
            raise BuildError(f"map embed should be a keyless maps/embed URL "
                             f"or satellite:lat,lng,zoom - got {url[:60]}")
        ll = re.search(r'!2d(-?[\d.]+)!3d(-?[\d.]+)', url)
        z  = re.search(r'!6i(\d+)', url)
        if not (ll and z):
            raise BuildError(f"cannot read coordinates from map embed: {url[:60]}")
        lat, lng, zoom = ll.group(2), ll.group(1), z.group(1)
    plain = f'https://maps.google.com/?q={lat},{lng}&t=k&z={zoom}'
    e = lambda s: html.escape(s, quote=True)
    return (
        '<figure class="guide-map">'
        f'<div class="guide-map__consent" data-map-src="{e(url)}" '
        f'data-map-title="{e(title)}">'
        '<button type="button" class="guide-map__load">Load map</button>'
        '<p class="guide-map__notice">Loading the map means you consent to '
        'Google&rsquo;s cookies. '
        f'<a href="{e(plain)}" target="_blank" rel="noopener noreferrer">'
        'Open in Google Maps instead</a>.</p>'
        '</div>'
        f'<figcaption>{html.escape(title)}</figcaption></figure>')

def render(body, pages, where, page_path):
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)   # editorial notes
    lines = body.split('\n')
    out, para, items, kind, first_para = [], [], [], None, None

    def flush_para():
        nonlocal para, first_para
        if not para: return
        text = ' '.join(para).strip()
        if text:
            if first_para is None and not text.startswith('!['):
                first_para = re.sub(r'[*\[\]]|\(@[^)]*\)', '', text)
            if re.fullmatch(r'!\[[^\]]*\]\([^)]+\)', text):
                out.append(inline(text, pages, where, page_path))
            else:
                out.append(f'<p>{inline(text, pages, where, page_path)}</p>')
        para = []

    def flush_list():
        nonlocal items, kind
        if not items: return
        tag = 'ul' if kind == 'ul' else 'ol'
        lis = ''.join(f'<li>{inline(i, pages, where, page_path)}</li>' for i in items)
        out.append(f'<{tag}>{lis}</{tag}>')
        items, kind = [], None

    for line in lines:
        s = line.strip()
        m = LIST_RE.match(s)
        mm = MAP_RE.match(s)
        if mm:
            flush_para(); flush_list()
            out.append(map_embed(mm.group(1), mm.group(2)))
        elif s.startswith('### '):
            flush_para(); flush_list()
            out.append(f'<h3>{inline(s[4:], pages, where, page_path)}</h3>')
        elif s.startswith('## '):
            flush_para(); flush_list()
            out.append(f'<h2>{inline(s[3:], pages, where, page_path)}</h2>')
        elif m:
            flush_para()
            k = 'ul' if m.group(1) else 'ol'
            if kind and k != kind: flush_list()
            kind = k; items.append(m.group(3))
        elif not s:
            flush_para()
            # a blank line does not close a list: items are separated by blanks
        else:
            flush_list(); para.append(s)
    flush_para(); flush_list()
    return '\n'.join(out), (first_para or '')

# -------------------------------------------------------------- templates ---

HEADER_BRAND = (
    '    <a class="site-header__brand" href="/">'
    '<img src="/assets/images/lessons/lessons-icon.png" alt="" width="32" height="32" '
    'class="app-icon app-icon--sm"><span>Lessons by Neil Beaver</span></a>')

# The same store badges as the home page. Apple's is served from their CDN;
# Google's is self-hosted because their brand guidelines require it.
HEADER_BADGES = '''    <div class="badge-group badge-group--header">
      <a href="https://apps.apple.com/gb/app/lessons-by-neil-beaver/id6768265585?itscg=30200&itsct=apps_box_badge&mttnsubad=6768265585"
         class="appstore-badge">
        <img src="https://toolbox.marketingtools.apple.com/api/v2/badges/download-on-the-app-store/black/en-us?releaseDate=1781222400"
             alt="Download Lessons by Neil Beaver on the App Store"
             width="120" height="40" decoding="async">
      </a>
      <a href="https://play.google.com/store/apps/details?id=com.neilbeaver.lessons"
         class="playstore-badge">
        <img src="/assets/images/google-play-badge.png"
             alt="Get Lessons by Neil Beaver on Google Play"
             width="646" height="250" decoding="async">
      </a>
    </div>'''

FOOTER = '''  <footer class="site-footer">
    <div class="container footer-inner">
      <div class="footer-brand">
        <img src="/assets/images/lessons/lessons-icon.png" alt=""
             class="app-icon app-icon--sm" width="32" height="32">
        <div><p class="footer-brand__name">Lessons by Neil Beaver</p></div>
      </div>
      <div class="footer-markets">
        <p class="footer-markets__label">Available in</p>
        <ul class="footer-markets__list">
          <li>&#127468;&#127463; United Kingdom</li>
          <li>&#127470;&#127466; Ireland</li>
          <li>&#127464;&#127486; Cyprus</li>
          <li>&#127474;&#127481; Malta</li>
        </ul>
      </div>
      <div class="footer-legal">
        <p>&copy; 2026 Neil Beaver. All rights reserved.</p>
        <p>
          <a href="/privacy">Privacy Policy</a>
          &nbsp;&middot;&nbsp;
          <a href="/terms">Terms of Use</a>
        </p>
      </div>
    </div>
  </footer>'''

def head(page, desc):
    title = ('Learn To Drive — A Free Guide for Learner Drivers'
             if page['path'] == 'index'
             else f"{page['title']} — Learn To Drive Guide")
    url = SITE + page['url']
    robots = '\n  <meta name="robots" content="noindex, follow">' if page['draft'] else ''
    e = lambda s: html.escape(s, quote=True)
    return f'''<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(title)} | Neil Beaver</title>
  <meta name="description" content="{e(desc)}">{robots}
  <link rel="canonical" href="{e(url)}">

  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Neil Beaver">
  <meta property="og:locale" content="en_GB">
  <meta property="og:url" content="{e(url)}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:image" content="{SITE}/assets/images/og-lessons.png">
  <meta name="twitter:card" content="summary_large_image">

  <meta name="theme-color" content="#1A3A5C">
  <link rel="icon" type="image/x-icon" href="/assets/favicons/favicon.ico">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/favicons/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/assets/favicons/favicon-16x16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicons/apple-touch-icon.png">
  <link rel="stylesheet" href="/style.css">
</head>
<body class="guide-body">'''

def breadcrumbs(page, pages):
    trail = [('Home', '/'), ('Learn To Drive', f'{GUIDE_URL}/')]
    if page.get('parent'):
        p = pages[page['parent']]
        trail.append((p['title'], p['url']))
    if page['path'] != 'index':
        trail.append((page['title'], page['url']))

    crumbs, items = [], []
    for i, (name, url) in enumerate(trail):
        last = i == len(trail) - 1
        e = html.escape(name)
        crumbs.append(f'<span aria-current="page">{e}</span>' if last
                      else f'<a href="{html.escape(url, quote=True)}">{e}</a>')
        items.append('{"@type":"ListItem","position":%d,"name":%s,"item":"%s"}'
                     % (i + 1, '"%s"' % name.replace('"', ''), SITE + url))
    nav = ('<nav class="breadcrumbs" aria-label="Breadcrumb"><div class="container">'
           + '<span class="breadcrumbs__sep">›</span>'.join(crumbs) + '</div></nav>')
    ld = ('<script type="application/ld+json">'
          '{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":['
          + ','.join(items) + ']}</script>')
    return nav, ld

def sidebar(page, tops):
    here = page['path']
    current_top = page.get('parent') or here
    # Open by default: a closed <details> hides its contents through UA
    # machinery that author CSS cannot reliably override, which left the
    # sidebar an empty box. script.js collapses it on small screens instead,
    # so with JavaScript off the nav is simply always visible.
    out = ['<details class="guide-nav" open>',
           '<summary class="guide-nav__title">Sections</summary>',
           '<div class="guide-nav__body">',
           '<nav aria-label="Guide sections"><ul class="guide-nav__list">']
    for t in tops:
        open_ = t['path'] == current_top
        cls = ' class="is-current"' if t['path'] == here else ''
        out.append(f'<li class="guide-nav__topic{" is-open" if open_ else ""}">')
        out.append(f'<a href="{t["url"]}"{cls}>{html.escape(t["title"])}</a>')
        if open_ and t['children']:
            out.append('<ul class="guide-nav__children">')
            for c in t['children']:
                ccls = ' class="is-current"' if c['path'] == here else ''
                draft = '<span class="guide-nav__soon">soon</span>' if c['draft'] else ''
                out.append(f'<li><a href="{c["url"]}"{ccls}>'
                           f'{html.escape(c["title"])}</a>{draft}</li>')
            out.append('</ul>')
        out.append('</li>')
    out.append('</ul></nav></div></details>')
    return ''.join(out)

def siblings_nav(page, pages, tops):
    """Previous / next within a topic, so a reader can work straight through."""
    if page['path'] == 'index' or not page.get('parent'): return ''
    sibs = pages[page['parent']]['children']
    idx = next((i for i, s in enumerate(sibs) if s['path'] == page['path']), None)
    if idx is None: return ''
    prev = sibs[idx - 1] if idx > 0 else pages[page['parent']]
    nxt  = sibs[idx + 1] if idx < len(sibs) - 1 else None
    parts = ['<nav class="guide-pager" aria-label="Within this section">']
    parts.append(f'<a class="guide-pager__prev" href="{prev["url"]}">'
                 f'<span>Previous</span>{html.escape(prev["title"])}</a>')
    if nxt:
        parts.append(f'<a class="guide-pager__next" href="{nxt["url"]}">'
                     f'<span>Next</span>{html.escape(nxt["title"])}</a>')
    parts.append('</nav>')
    return ''.join(parts)

def child_cards(page, tops, body_html):
    """An index of the section's pages, unless the prose already links them all."""
    kids = page.get('children') or []
    if not kids and page['path'] == 'index':
        kids = tops
    if not kids: return ''
    if all(k['url'] in body_html for k in kids): return ''
    cards = ''.join(
        f'<li><a href="{k["url"]}"><span class="guide-cards__name">'
        f'{html.escape(k["title"])}</span>'
        + ('<span class="guide-cards__soon">Coming soon</span>' if k['draft'] else '')
        + '</a></li>' for k in kids)
    return ('<section class="guide-cards"><h2>In this section</h2>'
            f'<ul class="guide-cards__list">{cards}</ul></section>')

def build_page(page, pages, tops):
    body_html, first_para = render(page['body'], pages,
                                   f"content/guide/{page['path']}.md", page['path'])
    desc = (first_para[:157].rsplit(' ', 1)[0] + '…') if len(first_para) > 158 else first_para
    crumb_nav, crumb_ld = breadcrumbs(page, pages)
    return '\n'.join([
        head(page, desc),
        '  <a class="skip-link" href="#guide-main">Skip to content</a>',
        '  <header class="site-header" id="site-header"><div class="container header-inner">',
        HEADER_BRAND,
        HEADER_BADGES,
        '  </div></header>',
        f'  {crumb_nav}',
        '  <div class="container guide-layout">',
        f'    {sidebar(page, tops)}',
        f'    <main class="guide-main" id="guide-main">',
        f'      <h1>{html.escape(page["title"])}</h1>',
        body_html,
        child_cards(page, tops, body_html),
        siblings_nav(page, pages, tops),
        '    </main>',
        '  </div>',
        FOOTER,
        '  <script src="/script.js"></script>',
        f'  {crumb_ld}',
        '</body>',
        '</html>',
    ])

def write_sitemap(pages):
    rows = list(STATIC_URLS)
    for p in sorted(pages.values(), key=lambda p: p['url']):
        if p['draft']: continue          # thin stubs stay out of the index
        prio = '0.8' if p['path'] == 'index' else ('0.7' if 'parent' not in p else '0.6')
        rows.append((p['url'], p.get('lastmod', str(date.today())), 'monthly', prio))
    body = '\n'.join(
        f'  <url>\n    <loc>{SITE}{u}</loc>\n    <lastmod>{m}</lastmod>\n'
        f'    <changefreq>{c}</changefreq>\n    <priority>{pr}</priority>\n  </url>'
        for u, m, c, pr in rows)
    open('sitemap.xml', 'w').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + body + '\n</urlset>\n')
    return len(rows)

def main():
    for r in csv.DictReader(open('tools/image-manifest.tsv'), delimiter='\t'):
        DIMS[(r['page'], os.path.basename(r['file']))] = {'dw': r['dw'], 'dh': r['dh']}

    pages = load_pages()
    tops  = tree(pages)
    for t in tops: pages[t['path']]['children'] = t['children']

    if os.path.isdir(OUT): shutil.rmtree(OUT)
    written = 0
    for p in pages.values():
        dest = os.path.join(OUT, 'index.html' if p['path'] == 'index'
                            else os.path.join(p['path'], 'index.html'))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, 'w').write(build_page(p, pages, tops))
        written += 1

    n = write_sitemap(pages)
    print(f"built {written} pages into {OUT}/")
    print(f"sitemap: {n} URLs ({sum(1 for p in pages.values() if p['draft'])} drafts excluded)")

if __name__ == '__main__':
    try:
        sys.exit(main())
    except BuildError as e:
        sys.exit(f"BUILD FAILED - {e}")
