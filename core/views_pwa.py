import json
from django.http import HttpResponse

_ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#4F46E5"/>
  <text x="256" y="340" text-anchor="middle"
        font-family="system-ui,-apple-system,sans-serif"
        font-weight="800" font-size="230" fill="white">PS</text>
</svg>"""

_MANIFEST = {
    "name": "Personal Shortcut",
    "short_name": "Shortcut",
    "description": "Your life, quietly organised.",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#F5F4FA",
    "theme_color": "#4F46E5",
    "orientation": "portrait-primary",
    "icons": [
        {
            "src": "/pwa-icon.svg",
            "sizes": "any",
            "type": "image/svg+xml",
            "purpose": "any maskable",
        }
    ],
}

_SERVICE_WORKER = """\
const CACHE = 'ps-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request).catch(() =>
      new Response(
        `<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
         <style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;
         height:100vh;margin:0;background:#F5F4FA;color:#6B7280;text-align:center;padding:2rem}</style></head>
         <body><div><p style="font-size:2rem;margin-bottom:1rem">📡</p>
         <p>You\\'re offline.</p><p style="margin-top:.5rem;font-size:.9rem">
         Open Personal Shortcut when connected.</p></div></body></html>`,
        { headers: { 'Content-Type': 'text/html' } }
      )
    )
  );
});
"""


def manifest(request):
    return HttpResponse(json.dumps(_MANIFEST, indent=2), content_type="application/manifest+json")


def service_worker(request):
    resp = HttpResponse(_SERVICE_WORKER, content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    return resp


def pwa_icon(request):
    return HttpResponse(_ICON_SVG, content_type="image/svg+xml")
