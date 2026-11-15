#!/usr/bin/env python3
"""Probe all channels in an M3U playlist for real playability.

Checks are deeper than an HTTP 200: fetches the playlist URL, walks into the
first variant if it's a master playlist, then fetches the first media segment.
A channel is ALIVE only if a segment actually downloads.

Usage: probe_channels.py <playlist.m3u> [output.json]
Writes a JSON ledger and prints a per-channel verdict.
"""
import json, re, sys, urllib.request, concurrent.futures, posixpath
from urllib.parse import urljoin

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TIMEOUT = 10

def fetch(url, max_bytes=65536):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, r.read(max_bytes), r.geturl()

def join(base, uri):
    if uri.startswith("http"): return uri
    return urljoin(base, uri)

def probe(name, url):
    try:
        status, body, final = fetch(url)
        text = body.decode("utf-8", "ignore")
        # master playlist -> walk into first variant
        if "#EXT-X-STREAM-INF" in text:
            uris = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
            if not uris:
                return name, url, "DEAD", "master playlist has no variants"
            url2 = join(final, uris[0])
            status, body, final = fetch(url2)
            text = body.decode("utf-8", "ignore")
        if "#EXTINF" not in text and "#EXT-X" not in text:
            return name, url, "DEAD", f"HTTP {status}, not an HLS playlist"
        segs = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
        if not segs:
            return name, url, "DEAD", "playlist has no segments"
        seg = join(final, segs[0])
        status, body, _ = fetch(seg, 4096)
        if status == 200 and len(body) > 0:
            return name, url, "ALIVE", f"segment {len(body)}B"
        return name, url, "DEAD", f"segment HTTP {status}"
    except Exception as e:
        return name, url, "DEAD", str(e)[:90]

def parse_m3u(path):
    chans, cur = [], None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("#EXTINF"):
            m = re.search(r'group-title="([^"]*)",(.*)$', line)
            cur = {"group": m.group(1) if m else "", "name": m.group(2) if m else line}
        elif line and not line.startswith("#") and cur:
            chans.append({**cur, "url": line}); cur = None
    return chans

if __name__ == "__main__":
    playlist = sys.argv[1] if len(sys.argv) > 1 else "tv-only.m3u"
    out = sys.argv[2] if len(sys.argv) > 2 else "tools/channel-status.json"
    chans = parse_m3u(playlist)
    print(f"probing {len(chans)} channels from {playlist} ...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(lambda c: probe(c["name"], c["url"]), chans):
            results.append({"name": res[0], "url": res[1], "status": res[2], "detail": res[3]})
            mark = "OK  " if res[2] == "ALIVE" else "DEAD"
            print(f"{mark} {res[0][:55]}")
    alive = sum(1 for r in results if r["status"] == "ALIVE")
    json.dump({"playlist": playlist, "probed": results}, open(out, "w"), indent=1)
    print(f"\n=== {alive}/{len(results)} ALIVE ===")
    for r in results:
        if r["status"] == "DEAD":
            print(f"DEAD: {r['name'][:60]} — {r['detail'][:80]}")
