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
import os, re, csv, html, shutil, sys, tomllib
from datetime import date

SITE      = 'https://www.neilbeaver.com'

# Maps JavaScript API key, used only by the satellite: form of @map. Browser
# API keys cannot be secret, so this one is restricted in the Cloud console to
# this site's referrers, to the Maps JavaScript API alone, and to a daily map
# load quota - the quota is what bounds the cost of a scraped key, since the
# JS API is billable. It is NOT the key the Roads app uses.
MAPS_API_KEY = 'AIzaSyAeVoRW-dA5WkLP4eAGk_RPwnjGBEnNCmI'
GUIDE_URL = '/lessons/guide'
OUT       = 'lessons/guide'
SRC       = 'content/guide'
IMG_URL   = '/assets/images/guide'
APPS_SRC  = 'content/apps'          # one .toml per app page
PROSE_SRC = 'content/pages'         # terms, privacy, import, 404
ICONS_SRC = 'content/icons.svg'     # <symbol>s shared by the module and card icons

# The guide is the one nav entry that is not an app; the app entries are built
# from content/apps at load time, so adding an app adds itself to the nav.
GUIDE_NAV = ('Learn To Drive', f'{GUIDE_URL}/')

# Who a page belongs to. Only the two brands that are not apps are named here:
# the site itself, for the home and legal pages, and the guide, which is Learn
# To Drive under the L-plate. An app's brand is its own name and icon, read
# from its .toml.
BRANDS = {
    'site':  dict(name='Neil Beaver', icon=None, badges=None),
    # An L-plate is a square sign with a printed black border, so the rounding
    # the app icons want would slice its corners off. square=True opts out.
    'guide': dict(name='Learn To Drive', badges='lessons', square=True,
                  icon='/assets/images/guide/l-plate.svg'),
}

def brand(key, apps):
    if key in BRANDS: return BRANDS[key]
    a = apps[key]
    return dict(name=a['name'], icon=a['icon'], square=False)

# Pages outside the guide that must stay in the sitemap. Their lastmod values
# are kept as they are so a guide rebuild does not churn every entry.
# How often each prose page is worth recrawling. Everything else in the sitemap
# is derived from what was built.
PROSE_FREQ = {'import': ('monthly', '0.7'), 'terms': ('yearly', '0.3'),
              'privacy': ('yearly', '0.3')}

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
NOTE_RE = re.compile(r'^@note (.+)$')          # a call-out box

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
    # Two forms. "satellite:lat,lng,zoom" renders through the Maps JavaScript
    # API, whose `satellite` map type is imagery with no labels - the Embed
    # API cannot do this, since its only display option is maptype and its
    # satellite layer is really hybrid. Anything else is a keyless
    # share-embed URL, which needs no key and shows labels.
    m = re.fullmatch(r'satellite:(-?[\d.]+),(-?[\d.]+),(\d+)', url)
    if m:
        lat, lng, zoom = m.group(1), m.group(2), m.group(3)
        plain = f'https://maps.google.com/?q={lat},{lng}&t=k&z={zoom}'
        e = lambda s: html.escape(str(s), quote=True)
        return (
            '<figure class="guide-map">'
            f'<div class="guide-map__consent" data-map-lat="{e(lat)}" '
            f'data-map-lng="{e(lng)}" data-map-zoom="{e(zoom)}" '
            f'data-map-key="{e(MAPS_API_KEY)}" data-map-title="{e(title)}">'
            '<button type="button" class="guide-map__load">Load map</button>'
            '<p class="guide-map__notice">Loading the map means you consent to '
            'Google&rsquo;s cookies. '
            f'<a href="{e(plain)}" target="_blank" rel="noopener noreferrer">'
            'Open in Google Maps instead</a>.</p>'
            '</div>'
            f'<figcaption>{html.escape(title)}</figcaption></figure>')

    if not url.startswith('https://www.google.com/maps/embed?pb='):
        raise BuildError(f"map embed should be a keyless maps/embed URL: {url[:60]}")
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
        mn = NOTE_RE.match(s)
        if mn:
            flush_para(); flush_list()
            out.append('<div class="prose-note"><p>'
                       + inline(mn.group(1), pages, where, page_path) + '</p></div>')
        elif mm:
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

def e(x):
    return html.escape(str(x), quote=True)

def lines(text):
    """A deliberate line break in a heading, kept out of the data as markup."""
    return '<br>'.join(e(p) for p in str(text).split('\n'))

# ------------------------------------------------------------------- icons ---

def icon_sprite():
    """The <symbol> definitions, inlined once per page that uses them.

    Nine module icons cover sixteen modules across the two apps, and the card
    icons overlap too, so they are defined once and referenced by <use>.
    """
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true">\n'
            + open(ICONS_SRC).read() + '</svg>')

def icon(name, cls, size):
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true"><use href="#icon-{e(name)}"/></svg>')

# ------------------------------------------------------------------ badges ---

APPLE_GLYPH = ('<svg viewBox="0 0 384 512" width="20" height="20" fill="currentColor" '
    'aria-hidden="true"><path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/></svg>')
PLAY_GLYPH = ('<svg viewBox="0 0 512 512" width="20" height="20" fill="currentColor" '
    'aria-hidden="true"><path d="M325.3 234.3L104.6 13l280.8 161.2-60.1 60.1zM47 0C34 6.8 25.3 19.2 25.3 35.3v441.3c0 16.1 8.7 28.5 21.7 35.3l256.6-256L47 0zm425.2 225.6l-58.9-34.1-65.7 64.5 65.7 64.5 60.1-34.1c17.4-9.8 17.4-36 0-46.7l-1.2.9zM104.6 499l280.8-161.2-60.1-60.1L104.6 499z"/></svg>')

def store_badges(app, group_class='', lazy=True, link_ids=False):
    """Apple and Google badges for an app that has shipped.

    Apple's artwork is served from their CDN; Google's is self-hosted because
    their brand guidelines require it, and it bakes in its own clear space,
    which is why it renders taller - see .playstore-badge in style.css.
    """
    st = app['store']
    ld = ' id="appstore-link"' if link_ids else ''
    lp = ' id="play-link"' if link_ids else ''
    load = ' loading="lazy"' if lazy else ''
    return f'''<div class="badge-group{group_class}">
          <a href="{e(st['apple'])}" class="appstore-badge"{ld}>
            <img src="{e(st['apple_badge'])}"
                 alt="Download {e(app['name'])} on the App Store"
                 width="120" height="40"{load} decoding="async">
          </a>
          <a href="{e(st['google'])}" class="playstore-badge"{lp}>
            <img src="/assets/images/google-play-badge.png"
                 alt="Get {e(app['name'])} on Google Play"
                 width="646" height="250"{load} decoding="async">
          </a>
        </div>'''

def soon_badge(store, glyph, cls):
    return (f'<span class="badge badge--{cls} badge--disabled" '
            f'aria-label="{e(store)} — Coming Soon">'
            f'<span class="badge__icon" aria-hidden="true">{glyph}</span>'
            '<span class="badge__text">'
            '<span class="badge__eyebrow">Coming Soon to</span>'
            f'<span class="badge__title">{e(store)}</span></span></span>')

def soon_badges(group_class=''):
    """Non-interactive pills for an app with no store listing yet.

    Swap these for store_badges() by giving the app a [store] table in its
    .toml - nothing else needs changing.
    """
    return (f'<div class="badge-group{group_class}">'
            + soon_badge('App Store', APPLE_GLYPH, 'appstore')
            + soon_badge('Google Play', PLAY_GLYPH, 'play') + '</div>')

def badges_for(app, group_class='', lazy=True, link_ids=False):
    return (store_badges(app, group_class, lazy, link_ids) if app.get('store')
            else soon_badges(group_class))

# ------------------------------------------------------------------ chrome ---

def nav_items(apps):
    return [(a['short_name'], f"/{a['slug']}/")
            for a in sorted(apps.values(), key=lambda a: a['slug'])] + [GUIDE_NAV]

def header(brand_key, current, apps):
    b = brand(brand_key, apps)
    NAV = nav_items(apps)
    sq = ' app-icon--square' if b.get('square') else ''
    ic = (f'<img src="{b["icon"]}" alt="" width="32" height="32" '
          f'class="app-icon app-icon--sm{sq}">') if b['icon'] else ''
    # The longest matching prefix wins, so a guide page marks Learn To Drive
    # rather than Lessons, even though /lessons/ is a prefix of both.
    here = max((u for _, u in NAV if current.startswith(u)), key=len, default=None)
    links = ''.join(
        f'<a href="{u}"{" aria-current=\"page\"" if u == here else ""}>{e(n)}</a>'
        for n, u in NAV)
    # An app or the guide names itself up here; the site's own pages do not,
    # since the home page says who this is in its own heading and repeating it
    # in the corner is just the same words twice.
    mark = (f'<a class="site-header__brand" href="/">{ic}'
            f'<span>{e(b["name"])}</span></a>') if b['icon'] else ''
    # Three slots, the outer two equal, so the nav is centred on the page
    # whether or not there is a brand on the left or badges on the right.
    return f'''  <header class="site-header" id="site-header">
    <div class="container header-inner">
      <div class="header-inner__start">{mark}</div>
      <nav class="site-nav" aria-label="Site">{links}</nav>
      <div class="header-inner__end"></div>
    </div>
  </header>'''

MARKETS = [('&#127468;&#127463;', 'United Kingdom'), ('&#127470;&#127466;', 'Ireland'),
           ('&#127464;&#127486;', 'Cyprus'), ('&#127474;&#127481;', 'Malta')]

def footer(brand_key, apps):
    b = brand(brand_key, apps)
    sq = ' app-icon--square' if b.get('square') else ''
    ic = (f'<img src="{b["icon"]}" alt="" width="32" height="32" '
          f'class="app-icon app-icon--sm{sq}">') if b['icon'] else ''
    markets = ''.join(f'<li>{f}&nbsp;{n}</li>' for f, n in MARKETS)
    return f'''  <footer class="site-footer">
    <div class="container footer-inner">
      <div class="footer-brand">
        {ic}
        <div><p class="footer-brand__name">{e(b["name"])}</p></div>
      </div>
      <div class="footer-markets">
        <p class="footer-markets__label">Available in</p>
        <ul class="footer-markets__list">{markets}</ul>
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

# Proves ownership of the domain to Google Search Console. It has to stay on
# the home page, and it has to be this exact string.
VERIFY = 'ftGvtdA16fvx6lBJQdFA9hr3gUy0wjTvugK0GFxUl-o'

def head(title, desc, url, og_image, og_type='website', og_alt='',
         noindex=False, preload=None, body_class='', verify=False):
    """Every page's <head>, so the address and the social tags cannot disagree.

    url is a path; it becomes the canonical and og:url against one SITE
    constant, which is the whole reason a domain change is one edit here
    rather than a find-and-replace across the site.
    """
    robots = '\n  <meta name="robots" content="noindex, follow">' if noindex else ''
    pre = (f'\n  <link rel="preload" as="image" href="{e(preload)}" fetchpriority="high">'
           if preload else '')
    cls = f' class="{body_class}"' if body_class else ''
    ver = f'\n  <meta name="google-site-verification" content="{VERIFY}">' if verify else ''
    return f'''<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(title)}</title>
  <meta name="description" content="{e(desc)}">{robots}{ver}
  <link rel="canonical" href="{SITE}{e(url)}">

  <meta property="og:type" content="{og_type}">
  <meta property="og:site_name" content="Neil Beaver">
  <meta property="og:locale" content="en_GB">
  <meta property="og:url" content="{SITE}{e(url)}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:image" content="{SITE}{e(og_image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{e(og_alt or title)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{e(title)}">
  <meta name="twitter:description" content="{e(desc)}">
  <meta name="twitter:image" content="{SITE}{e(og_image)}">

  <meta name="theme-color" content="#1A3A5C">{pre}
  <link rel="icon" type="image/x-icon" href="/assets/favicons/favicon.ico">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/favicons/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/assets/favicons/favicon-16x16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicons/apple-touch-icon.png">
  <link rel="stylesheet" href="/style.css">
</head>
<body{cls}>'''

# --------------------------------------------------------------- app pages ---

def device_display(mock, first=False):
    """The tablet/phone mockup pair with its segmented switcher.

    script.js scopes the switcher to the enclosing .device-display, so a page
    can carry several of these independently.
    """
    t, ph = mock['tablet'], mock['phone']
    prio = ' fetchpriority="high" decoding="async"' if first else ' loading="lazy" decoding="async"'
    return f'''<div class="device-display">
            <div class="device-switcher" role="group" aria-label="Switch device preview">
              <button class="device-switcher__btn is-active" data-device="tablet" aria-pressed="true">
                <svg viewBox="0 0 14 18" width="11" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="1" y="1" width="12" height="16" rx="2"/>
                  <circle cx="7" cy="14.5" r="0.8" fill="currentColor" stroke="none"/>
                </svg>
                Tablet
              </button>
              <button class="device-switcher__btn" data-device="phone" aria-pressed="false">
                <svg viewBox="0 0 10 18" width="8" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="1" y="1" width="8" height="16" rx="2.5"/>
                  <line x1="3.5" y1="15" x2="6.5" y2="15"/>
                </svg>
                Phone
              </button>
            </div>
            <div class="device-view device-view--tablet">
              <div class="ipad-mockup ipad-mockup--portrait">
                <div class="ipad-mockup__shell">
                  <div class="ipad-mockup__camera" aria-hidden="true"></div>
                  <div class="ipad-mockup__screen">
                    <img src="{e(t['src'])}" alt="{e(t['alt'])}"
                         class="ipad-mockup__screenshot"
                         width="{t['width']}" height="{t['height']}"{prio}>
                  </div>
                </div>
              </div>
            </div>
            <div class="device-view device-view--phone" hidden>
              <div class="iphone-mockup">
                <div class="iphone-mockup__shell">
                  <div class="iphone-mockup__screen">
                    <img src="{e(ph['src'])}" alt="{e(ph['alt'])}"
                         class="iphone-mockup__screenshot"
                         width="{ph['width']}" height="{ph['height']}" loading="lazy" decoding="async">
                  </div>
                  <div class="iphone-mockup__home-bar" aria-hidden="true"></div>
                </div>
              </div>
            </div>
          </div>'''

CONTACT = ('<p class="contact-note">Questions or feedback? '
           '<a href="#" class="js-email" data-u="ebobfbhynccf" data-d="tznvy.pbz">'
           'Send us an email</a></p>')

def app_schema(app):
    """SoftwareApplication for one app.

    An app with no store listing gets no `offers`: advertising a price for
    something nobody can buy is exactly the kind of claim structured data is
    not for.
    """
    parts = ['"@type":"SoftwareApplication"',
             f'"@id":"{SITE}/{app["slug"]}/#app"',
             f'"name":{json_str(app["name"])}',
             f'"description":{json_str(app["description"])}',
             '"applicationCategory":"EducationalApplication"',
             '"operatingSystem":"iOS, iPadOS, Android"',
             f'"url":"{SITE}/{app["slug"]}/"',
             f'"image":"{SITE}{app["og_image"]}"',
             '"author":{"@type":"Person","name":"Neil Beaver"}']
    if app.get('offer'):
        o = app['offer']
        regions = ','.join(f'"{r}"' for r in o['regions'])
        parts.append('"offers":{"@type":"Offer","price":"%s","priceCurrency":"%s",'
                     '"eligibleRegion":[%s]}' % (o['price'], o['currency'], regions))
    return '{' + ','.join(parts) + '}'

def json_str(x):
    return '"' + str(x).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'

def app_page(app, apps):
    slug, url = app['slug'], f'/{app["slug"]}/'
    hero, about, mods, cta = app['hero'], app['about'], app['modules'], app['cta']

    cards = ''.join(f'''<div class="card">
            <div class="card__icon" aria-hidden="true">{icon(c["icon"], "", 24)}</div>
            <h3>{e(c["title"])}</h3>
            <p>{e(c["body"])}</p>
          </div>''' for c in about['cards'])

    items = []
    for m in mods['list']:
        topics = ''.join(f'<li>{e(t)}</li>' for t in m['topics'])
        # The nine Lessons modules are the nine guide sections, so each one
        # can point at the written version of itself.
        more = (f'\n              <p class="module__guide"><a href="{m["guide"]}">'
                f'Read about {e(m["title"]).lower()} in the guide</a></p>'
                if m.get('guide') else '')
        n = len(m['topics'])
        items.append(f'''<details class="module">
              <summary class="module__header">
                {icon(m["icon"], "module__icon", 18)}
                <span class="module__title">{e(m["title"])}</span>
                <span class="module__count">{n} topic{"" if n == 1 else "s"}</span>
                <svg class="module__chevron" width="16" height="16" aria-hidden="true"><use href="#icon-chevron"/></svg>
              </summary>
              <ul class="module__topics">{topics}</ul>{more}
            </details>''')

    markets = ''.join(f'<span class="market">{f}&thinsp;{n}</span>'
                      for f, n in [('&#127468;&#127463;', 'UK'), ('&#127470;&#127466;', 'Ireland'),
                                   ('&#127464;&#127486;', 'Cyprus'), ('&#127474;&#127481;', 'Malta')])

    return '\n'.join([
      head(app['title'], app['description'], url, app['og_image'],
           og_type='website', og_alt=hero['tablet']['alt'],
           preload=hero['tablet']['src']),
      '  <a class="skip-link" href="#main">Skip to content</a>',
      '  ' + icon_sprite(),
      header(slug, url, apps),
      '  <main id="main">',
      f'''    <section class="hero">
      <div class="container hero-inner">
        <div class="hero-content">
          <h1 class="hero-heading">{lines(hero["heading"])}</h1>
          <p class="hero-subheading">{e(hero["subheading"])}</p>
          {badges_for(app, "", lazy=False, link_ids=True)}
          <p class="hero-markets">Available in:&ensp;<span class="hero-markets__countries">{markets}</span></p>
        </div>
        <div class="hero-device">{device_display(hero, first=True)}</div>
      </div>
    </section>

    <section class="about">
      <div class="container">
        <div class="about-icon-wrap">
          <img src="{e(app["icon"])}" alt="{e(app["name"])}" class="app-icon app-icon--lg" width="120" height="120">
        </div>
        <div class="section-intro">
          <h2>{lines(about["heading"])}</h2>
          <p>{e(about["subheading"])}</p>
        </div>
        <div class="cards">{cards}</div>
      </div>
    </section>

    <section class="modules">
      <div class="container">
        <div class="section-intro">
          <h2>{e(mods["heading"])}</h2>
          <p>{e(mods["intro"])}</p>
        </div>
        <div class="modules-layout">
          <div class="modules-list">{"".join(items)}</div>
          {device_display(mods)}
        </div>
      </div>
    </section>

    <section class="download-cta">
      <div class="container download-cta-inner">
        <h2>{e(cta["heading"])}</h2>
        <p>{e(cta["lead"])}</p>
        {badges_for(app, " badge-group--center")}
        {CONTACT}
      </div>
    </section>''',
      '  </main>',
      footer(slug, apps),
      '  <script src="/script.js"></script>',
      '  <script type="application/ld+json">'
      '{"@context":"https://schema.org","@graph":[' + app_schema(app) + ']}</script>',
      '</body>',
      '</html>',
    ])

# -------------------------------------------------------------- home page ---

def faq_blocks(faq):
    """The questions, and the same questions as FAQPage markup.

    Answers are written as markdown in content/home.toml and go through the
    guide's inline() renderer, so a link in an answer is written once rather
    than kept in step across the visible copy and the structured data.
    """
    items, ld = [], []
    for i, f in enumerate(faq):
        ans = '\n'.join(f'<p>{inline(par, {}, "content/home.toml", "")}</p>'
                         for par in f['a'].split('\n') if par.strip())
        items.append(f'''<details class="module">
              <summary class="module__header">
                <span class="module__title">{e(f["q"])}</span>
                <svg class="module__chevron" width="16" height="16" aria-hidden="true"><use href="#icon-chevron"/></svg>
              </summary>
              <div class="faq__answer">{ans}</div>
            </details>''')
        ld.append('{"@type":"Question","name":%s,"acceptedAnswer":'
                  '{"@type":"Answer","text":%s}}'
                  % (json_str(f['q']), json_str(re.sub(r'\[([^\]]+)\]\([^)]+\)',
                                                      r'\1', f['a']))))
    return ''.join(items), ','.join(ld)

def home_page(home, apps):
    cards = ''.join(f'''<a class="product" href="{e(p["url"])}">
            <img src="{e(p["icon"])}" alt="" width="96" height="96"
                 class="product__icon{" product__icon--square" if p.get("square") else ""}">
            <h2 class="product__name">{e(p["name"])}</h2>
            <p class="product__status">{e(p["status"])}</p>
            <p class="product__body">{e(p["body"])}</p>
            <span class="product__more">Find out more</span>
          </a>''' for p in home['products'])

    faq_html, faq_ld = faq_blocks(home['faq'])
    about = ''.join(f'<p>{e(par)}</p>' for par in home['about']['body'])

    graph = ('{"@type":"WebSite","@id":"%s/#website","url":"%s/","name":"Neil Beaver",'
             '"inLanguage":"en-GB"}' % (SITE, SITE)
             + ',{"@type":"Person","@id":"%s/#neil","name":"Neil Beaver",'
               '"jobTitle":"Approved Driving Instructor",'
               '"url":"%s/","knowsAbout":["Driving instruction","Learning to drive",'
               '"UK driving test"]}' % (SITE, SITE)
             + ''.join(',' + app_schema(a) for a in sorted(apps.values(),
                                                           key=lambda a: a['slug']))
             + ',{"@type":"FAQPage","@id":"%s/#faq","mainEntity":[%s]}' % (SITE, faq_ld))

    return '\n'.join([
      head(home['title'], home['description'], '/', home['og_image'],
           verify=True),
      '  <a class="skip-link" href="#main">Skip to content</a>',
      '  ' + icon_sprite(),
      header('site', '/', apps),
      '  <main id="main">',
      f'''    <section class="home-hero">
      <div class="container">
        <h1><span class="home-hero__name">{e(home["hero"]["name"])}</span>{lines(home["hero"]["heading"])}</h1>
      </div>
    </section>

    <section class="products">
      <div class="container">
        <div class="products__grid">{cards}</div>
      </div>
    </section>

    <section class="about">
      <div class="container">
        <div class="section-intro">
          <h2>{lines(home["about"]["heading"])}</h2>
        </div>
        <div class="home-about__body">{about}</div>
      </div>
    </section>

    <section class="faq" id="faq">
      <div class="container">
        <div class="section-intro section-intro--light">
          <h2>{e(home["faq_heading"])}</h2>
        </div>
        <div class="modules-list">{faq_html}</div>
      </div>
    </section>''',
      '  </main>',
      footer('site', apps),
      '  <script src="/script.js"></script>',
      '  <script type="application/ld+json">'
      '{"@context":"https://schema.org","@graph":[' + graph + ']}</script>',
      '</body>',
      '</html>',
    ])

def load_home():
    return tomllib.load(open('content/home.toml', 'rb'))

# ------------------------------------------------------------- prose pages ---

def prose_page(page, apps):
    """Terms, privacy, the import guide and 404: a column of text under the
    shared chrome. They were hand-written HTML carrying their own copy of the
    header and footer, which is why a change to either used to mean five edits.
    """
    body, _ = render(page['body'], {}, f"content/pages/{page['path']}.md", '')
    url = '/' + page['path'] if page['path'] != '404' else '/404'
    updated = (f'<p class="last-updated">Last updated: {e(page["updated"])}</p>'
               if page.get('updated') else '')
    return '\n'.join([
      head(page['seo_title'] + ' | Neil Beaver', page['description'], url,
           '/assets/images/og-lessons.png', og_type='article',
           noindex=page.get('noindex') == 'true'),
      '  <a class="skip-link" href="#main">Skip to content</a>',
      '  ' + icon_sprite(),
      header(page['brand'], url, apps),
      '  <main id="main">',
      '    <section class="prose-page">',
      '      <div class="container">',
      '        <a href="/" class="prose-back">'
      '<svg width="16" height="16" aria-hidden="true" style="transform:rotate(90deg)">'
      '<use href="#icon-chevron"/></svg>Back</a>',
      f'        <h1>{e(page["title"])}</h1>',
      f'        {updated}',
      body,
      '      </div>',
      '    </section>',
      '  </main>',
      footer(page['brand'], apps),
      '  <script src="/script.js"></script>',
      '</body>',
      '</html>',
    ])

def load_prose():
    pages = []
    if not os.path.isdir(PROSE_SRC): return pages
    for f in sorted(os.listdir(PROSE_SRC)):
        if not f.endswith('.md'): continue
        raw = open(os.path.join(PROSE_SRC, f)).read()
        _, fm, body = raw.split('---\n', 2)
        meta = dict(re.findall(r'^(\w+): (.*)$', fm, re.M))
        # A value may be quoted so it can contain a colon, which bare YAML
        # would read as a nested key.
        meta = {k: v[1:-1] if len(v) > 1 and v[0] == v[-1] == '"' else v
                for k, v in meta.items()}
        meta['body'] = body.strip()
        pages.append(meta)
    return pages

def load_apps():
    apps = {}
    if not os.path.isdir(APPS_SRC): return apps
    for f in sorted(os.listdir(APPS_SRC)):
        if f.endswith('.toml'):
            d = tomllib.load(open(os.path.join(APPS_SRC, f), 'rb'))
            apps[d['slug']] = d
    return apps

def breadcrumbs(page, pages):
    trail = [('Home', '/'), ('Lessons', '/lessons/'),
             ('Learn To Drive', f'{GUIDE_URL}/')]
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
                out.append(f'<li><a href="{c["url"]}"{ccls}>'
                           f'{html.escape(c["title"])}</a></li>')
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
    """An index of the section's pages, at the foot of every section page.

    Every section ends the same way, so a reader always knows where the next
    page is. The guide home is the exception: it introduces each section in its
    own words, and a bare list of the same links underneath would only repeat
    itself.
    """
    if page['path'] == 'index':
        kids = page.get('children') or tops
        if all(k['url'] in body_html for k in kids): return ''
    else:
        kids = page.get('children') or []
    if not kids: return ''
    cards = ''.join(
        f'<li><a href="{k["url"]}"><span class="guide-cards__name">'
        f'{html.escape(k["title"])}</span></a></li>' for k in kids)
    return ('<section class="guide-cards"><h2>In this section</h2>'
            f'<ul class="guide-cards__list">{cards}</ul></section>')

def build_page(page, pages, tops, apps):
    body_html, first_para = render(page['body'], pages,
                                   f"content/guide/{page['path']}.md", page['path'])
    desc = (first_para[:157].rsplit(' ', 1)[0] + '…') if len(first_para) > 158 else first_para
    crumb_nav, crumb_ld = breadcrumbs(page, pages)
    title = ('Learn To Drive — A Free Guide for Learner Drivers | Neil Beaver'
             if page['path'] == 'index'
             else f"{page['title']} — Learn To Drive Guide | Neil Beaver")
    return '\n'.join([
        head(title, desc, page['url'], '/assets/images/og-lessons.png',
             og_type='article', noindex=page['draft'], body_class='guide-body'),
        '  <a class="skip-link" href="#guide-main">Skip to content</a>',
        header('guide', page['url'], apps),
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
        footer('guide', apps),
        '  <script src="/script.js"></script>',
        f'  {crumb_ld}',
        '</body>',
        '</html>',
    ])

def file_date(path):
    """A page's lastmod from its source, rather than a date typed by hand that
    stops being true the moment the page is edited."""
    return date.fromtimestamp(os.path.getmtime(path)).isoformat()

def write_sitemap(pages, apps, prose):
    rows = [('/', file_date('content/home.toml'), 'weekly', '1.0')]
    for pg in prose:
        if pg.get('noindex') == 'true': continue
        freq, prio = PROSE_FREQ.get(pg['path'], ('yearly', '0.3'))
        rows.append(('/' + pg['path'],
                     file_date(os.path.join(PROSE_SRC, pg['path'] + '.md')),
                     freq, prio))
    for a in sorted(apps.values(), key=lambda a: a['slug']):
        rows.append((f"/{a['slug']}/",
                     file_date(os.path.join(APPS_SRC, a['slug'] + '.toml')),
                     'monthly', '0.9'))
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

    apps  = load_apps()
    pages = load_pages()
    tops  = tree(pages)
    for t in tops: pages[t['path']]['children'] = t['children']

    if os.path.isdir(OUT): shutil.rmtree(OUT)
    written = 0
    for p in pages.values():
        dest = os.path.join(OUT, 'index.html' if p['path'] == 'index'
                            else os.path.join(p['path'], 'index.html'))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, 'w').write(build_page(p, pages, tops, apps))
        written += 1

    for a in apps.values():
        os.makedirs(a['slug'], exist_ok=True)
        open(os.path.join(a['slug'], 'index.html'), 'w').write(app_page(a, apps))

    home = load_home()
    open('index.html', 'w').write(home_page(home, apps))

    prose = load_prose()
    for pg in prose:
        open(pg['out'], 'w').write(prose_page(pg, apps))

    n = write_sitemap(pages, apps, prose)
    print(f"built {written} guide pages into {OUT}/")
    print(f"built {len(apps)} app pages: {', '.join('/' + s + '/' for s in sorted(apps))}")
    print("built the home page into index.html")
    print(f"built {len(prose)} prose pages: {', '.join(p['out'] for p in prose)}")
    print(f"sitemap: {n} URLs ({sum(1 for p in pages.values() if p['draft'])} drafts excluded)")

if __name__ == '__main__':
    try:
        sys.exit(main())
    except BuildError as e:
        sys.exit(f"BUILD FAILED - {e}")
