#!/usr/bin/env python3
"""Verify the built HTML.

The guide's markdown renderer is hand-written, so this is what guarantees it is
total over the content: any construct it failed to handle shows up as leftover
markdown in the output and fails the build. It also resolves every internal
link against the files on disk, which catches @page-id typos and trailing-slash
mistakes, and parses each page to catch unbalanced or unescaped markup.
"""
import os, re, sys
from html.parser import HTMLParser

ROOT = 'lessons/guide'
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
    path = url.split('#')[0].split('?')[0]
    if not path.startswith('/'): return None
    if path.endswith('/'):  return path.lstrip('/') + 'index.html'
    if '.' in os.path.basename(path): return path.lstrip('/')
    return path.lstrip('/') + '.html'      # flat pages: /privacy -> privacy.html

def main():
    problems, pages = [], []
    for root, _, files in os.walk(ROOT):
        for f in files:
            if f.endswith('.html'): pages.append(os.path.join(root, f))

    for p in sorted(pages):
        src = open(p).read()
        body = src.split('<body', 1)[-1]
        body_no_ld = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.S)
        for rx, why in LEFTOVER:
            if rx.search(body_no_ld):
                problems.append(f"{p}: {why} -> {rx.search(body_no_ld).group(0)!r}")

        b = Balance(); b.feed(src)
        for e in b.err: problems.append(f"{p}: {e}")
        if b.stack: problems.append(f"{p}: unclosed {b.stack}")

        for m in re.finditer(r'(?:href|src)="([^"]+)"', src):
            u = m.group(1)
            if u.startswith(('http', 'mailto:', '#', 'data:')): continue
            target = url_to_file(u)
            if target and not os.path.exists(target):
                problems.append(f"{p}: broken link {u} -> {target}")

    print(f"checked {len(pages)} pages, {len(problems)} problems")
    for x in problems[:40]: print("  ", x)
    if len(problems) > 40: print(f"   ... and {len(problems)-40} more")
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
