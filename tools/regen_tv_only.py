#!/usr/bin/env python3
"""Regenerate tv-only.m3u from background.m3u.

Filter: drop all group-title="Radio" channels EXCEPT any named 'Lot Radio'.
"""
import re
import sys

SRC = "background.m3u"
DST = "tv-only.m3u"


def main() -> None:
    bg = open(SRC).read().splitlines()
    out = ["#EXTM3U"]
    keep = False
    for line in bg:
        if line.startswith("#EXTINF"):
            m = re.search(r'group-title="([^"]*)"', line)
            group = m.group(1) if m else ""
            name = line.split(",", 1)[-1].strip()
            keep = (group != "Radio") or ("Lot Radio" in name)
            if keep:
                out.append(line)
        elif keep and line.strip():
            out.append(line)
    content = "\n".join(out) + "\n"
    if open(DST).read() == content:
        print("tv-only.m3u unchanged")
        return
    open(DST, "w").write(content)
    print("tv-only.m3u regenerated")


if __name__ == "__main__":
    sys.exit(main())
