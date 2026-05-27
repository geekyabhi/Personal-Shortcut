import json
import urllib.request
from functools import lru_cache

from django.http import HttpResponse, HttpResponseRedirect

_CL_BASE = "https://res.cloudinary.com/dciwki8ry/image/upload"
_CL_IMG  = "v1779852541/Gemini_Generated_Image_z11dhpz11dhpz11d-Photoroom_zo41z4.png"


@lru_cache(maxsize=4)
def _fetch_icon(w, h):
    url = f"{_CL_BASE}/w_{w},h_{h},c_fill/{_CL_IMG}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read()

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
            "src": "/apple-touch-icon.png",
            "sizes": "180x180",
            "type": "image/png",
            "purpose": "any maskable",
        },
        {
            "src": "/pwa-icon.svg",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any maskable",
        },
    ],
}

_SERVICE_WORKER = """\
const CACHE = 'ps-v2';

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
    resp = HttpResponse(_fetch_icon(512, 512), content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


def apple_touch_icon(request):
    resp = HttpResponse(_fetch_icon(180, 180), content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp
