#!/usr/bin/env python3
"""Build the merged XMLTV guide + enrich tv-only.m3u with tvg-id mappings.

Sources: mjh.nz Samsung TV Plus (all) + Plex (all) XMLTV feeds.
Output:  epg/guide.xml — only channels that match our playlist, so Jellyfin
         parses a small file instead of 170k programmes.
Also rewrites tv-only.m3u adding tvg-id="..." to every #EXTINF that has a match
(Radio group still filtered to The Lot Radio only — filtering happens in the
tv-only generator; this script only adds attributes).

Usage: python3 tools/build_epg.py
"""
import gzip, re, sys, time, os, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EPG_DIR = REPO / "epg"
FEEDS = [
    ("samsung", "https://i.mjh.nz/SamsungTVPlus/all.xml.gz"),
    ("plex", "https://i.mjh.nz/Plex/all.xml.gz"),
]
UA = {"User-Agent": "Mozilla/5.0"}
FRESH_SECS = 6 * 3600

def fetch_feed(name, url):
    cache = EPG_DIR / f"{name}.xml.gz"
    EPG_DIR.mkdir(exist_ok=True)
    if not cache.exists() or time.time() - cache.stat().st_mtime > FRESH_SECS:
        req = urllib.request.Request(url, headers=UA)
        cache.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return gzip.open(cache, "rt", errors="ignore").read()

def our_names():
    names = []
    for line in open(REPO / "tv-only.m3u", encoding="utf-8"):
        if line.startswith("#EXTINF"):
            m = re.search(r'group-title="[^"]*",(.*)$', line)
            if m:
                names.append(m.group(1).strip().lower())
    return names

def main():
    ours = set(our_names())
    matches = {}   # our_name_lower -> (source, channel_id)
    blocks = []    # per-feed: (channel_xml_blocks, programme_xml_blocks)
    for name, url in FEEDS:
        try:
            txt = fetch_feed(name, url)
        except Exception as e:
            print(f"feed {name} failed: {e}", file=sys.stderr)
            continue
        chan_blocks = [m.group(0) for m in re.finditer(r'<channel\b[^>]*>.*?</channel>', txt, re.S)]
        prog_blocks = [m.group(0) for m in re.finditer(r'<programme\b[^>]*>.*?</programme>', txt, re.S)]
        id_for_our = {}
        for block in chan_blocks:
            cid = re.search(r'<channel\b[^>]*\bid="([^"]+)"', block)
            dn = re.search(r'<display-name>([^<]+)</display-name>', block)
            if cid and dn and dn.group(1).strip().lower() in ours:
                id_for_our[dn.group(1).strip().lower()] = cid.group(1)
        keep_ids = set(id_for_our.values())
        for low, cid in id_for_our.items():
            matches.setdefault(low, (name, cid))   # samsung wins over plex
        kept_ch = [b for b in chan_blocks
                   if re.search(r'\bid="([^"]+)"', b).group(1) in keep_ids]
        kept_pr = [b for b in prog_blocks
                   if re.search(r'\bchannel="([^"]+)"', b).group(1) in keep_ids]
        blocks.append((kept_ch, kept_pr))
        print(f"{name}: {len(kept_ch)} channels, {len(kept_pr)} programmes kept")

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE tv SYSTEM "xmltv.dtd">', '<tv source-info-name="mjh.nz merge">']
    for ch, _ in blocks:
        out += ch
    for _, pr in blocks:
        out += pr
    out.append("</tv>")
    guide = EPG_DIR / "guide.xml"
    guide.write_text("\n".join(out), encoding="utf-8")
    print(f"guide.xml: {sum(len(c) for c,_ in blocks)} channels, "
          f"{sum(len(p) for _,p in blocks)} programmes, {guide.stat().st_size // 1024} KB")

    # enrich tv-only.m3u with tvg-id
    src = open(REPO / "tv-only.m3u", encoding="utf-8").read().splitlines()
    out_lines, enriched = [], 0
    for line in src:
        if line.startswith("#EXTINF") and "tvg-id=" not in line:
            m = re.search(r'group-title="[^"]*",(.*)$', line)
            if m:
                hit = matches.get(m.group(1).strip().lower())
                if hit:
                    line = re.sub(r'(group-title="[^"]*")',
                                  r'\1 ' + f'tvg-id="{hit[1]}"', line, count=1)
                    enriched += 1
        out_lines.append(line)
    (REPO / "tv-only.m3u").write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"tv-only.m3u: +{enriched} tvg-id attributes this pass "
          f"({sum(1 for l in out_lines if 'tvg-id=' in l)} total)")

if __name__ == "__main__":
    main()
