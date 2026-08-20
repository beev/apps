#!/usr/bin/env python3
"""Serve the site locally and rebuild whenever content or templates change.

The site is generated, so editing content/*.md has no effect on the preview
until tools/build.py runs. This does that automatically: edit a file, refresh
the browser.

Stdlib only, polling rather than filesystem events - there are ~60 files to
watch, so a twice-a-second stat costs nothing and avoids a dependency.

Usage: python3 tools/serve.py [port]        (default 8000)
"""
import os, sys, time, subprocess, threading, functools, http.server


ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH = ['content', 'tools/build.py', 'style.css', 'script.js']
PORT  = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

def snapshot():
    """mtimes of everything worth rebuilding for."""
    seen = {}
    for target in WATCH:
        p = os.path.join(ROOT, target)
        if os.path.isfile(p):
            seen[p] = os.path.getmtime(p)
        for base, _, files in os.walk(p):
            for f in files:
                if f.startswith('.'): continue
                fp = os.path.join(base, f)
                try: seen[fp] = os.path.getmtime(fp)
                except OSError: pass
    return seen

def build():
    r = subprocess.run([sys.executable, 'tools/build.py'], cwd=ROOT,
                       capture_output=True, text=True)
    stamp = time.strftime('%H:%M:%S')
    if r.returncode != 0:
        # A build error means the last good HTML is still being served, so say
        # so loudly rather than letting the browser show stale pages silently.
        print(f"[{stamp}] BUILD FAILED - serving the previous version")
        print((r.stdout + r.stderr).strip())
    else:
        print(f"[{stamp}] {r.stdout.strip().splitlines()[0]}")

def watch():
    last = snapshot()
    while True:
        time.sleep(0.5)
        now = snapshot()
        if now != last:
            changed = [os.path.relpath(p, ROOT) for p in now
                       if last.get(p) != now.get(p)]
            print(f"changed: {', '.join(sorted(changed)[:3])}"
                  + (' …' if len(changed) > 3 else ''))
            build()
            last = snapshot()

class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve with GitHub Pages' URL rules rather than plain file semantics.

    Pages resolves /privacy to privacy.html, and redirects /lessons/guide to
    the trailing-slash form. The stdlib handler does the redirect but not the
    extensionless lookup, so every address this site actually publishes -
    /privacy, /terms, /import - used to 404 in the preview while working in
    production. The convention is that addresses are written without .html,
    so the preview has to understand them or it cannot test the real links.
    """
    def send_head(self):
        path = self.path.partition('?')[0]
        target = self.translate_path(path)
        if not os.path.exists(target) and os.path.isfile(target + '.html'):
            head, sep, query = self.path.partition('?')
            self.path = head + '.html' + sep + query
        return super().send_head()

    def send_error(self, code, message=None, explain=None):
        """Serve 404.html for misses, as Pages does, so it gets exercised."""
        page = os.path.join(ROOT, '404.html')
        if code == 404 and os.path.isfile(page):
            body = open(page, 'rb').read()
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)

    def end_headers(self):
        # otherwise a rebuilt page can sit in the browser cache
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, *a): pass

if __name__ == '__main__':
    sys.stdout.reconfigure(line_buffering=True)   # keep the log useful when piped
    build()
    threading.Thread(target=watch, daemon=True).start()
    handler = functools.partial(Handler, directory=ROOT)
    print(f"\n  http://localhost:{PORT}/\n  watching {', '.join(WATCH)} — Ctrl-C to stop\n")
    http.server.ThreadingHTTPServer(('', PORT), handler).serve_forever()
