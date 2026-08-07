#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Populate venue lat/lon in event YAMLs from their meetup.com pages.

Meetup's server-rendered HTML embeds the venue as "lat":60.19852,"lng":24.931107.
Idempotent: skips files that already have a lat, and files without a venue block.

Usage: uv run scrape_geo.py [events/*.yaml]
"""

import re
import sys
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"


def scrape(url: str) -> tuple[str, str] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode()
    m = re.search(r'"lat":(-?\d+\.\d+),"lng":(-?\d+\.\d+)', html)
    return m.groups() if m else None


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(
        (Path(__file__).parent / "events").glob("*.yaml")
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        murl = re.search(r"url: (https://www\.meetup\.com/\S+)", text)
        if "venue:" not in text or not murl:
            continue
        if re.search(r"^  lat:", text, re.M):
            print(f"{path.name}: already has lat, skipping")
            continue
        try:
            coords = scrape(murl.group(1))
        except OSError as e:
            print(f"{path.name}: fetch failed ({e})")
            continue
        if not coords:
            print(f"{path.name}: no coordinates on meetup page")
            continue
        lat, lon = coords
        lines = text.splitlines(keepends=True)
        i = next(n for n, line in enumerate(lines) if line.startswith("venue:")) + 1
        while i < len(lines) and lines[i].startswith("  "):
            i += 1
        lines[i:i] = [f"  lat: {lat}\n", f"  lon: {lon}\n"]
        path.write_text("".join(lines), encoding="utf-8")
        print(f"{path.name}: {lat}, {lon}")


if __name__ == "__main__":
    main()
