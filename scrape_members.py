#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Update member_count in community.yaml from the meetup.com group page.

Meetup's server-rendered HTML embeds "memberCounts":{...,"all":1234,...}.
Once we're off Meetup, edit community.yaml by hand instead.

Usage: uv run scrape_members.py
"""

import datetime
import re
import urllib.request
from pathlib import Path

URL = "https://www.meetup.com/pydata-helsinki/"
UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"
COMMUNITY = Path(__file__).parent / "community.yaml"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode()
    m = re.search(r'"memberCounts":\{[^{}]*?"all":(\d+)', html)
    if not m:
        raise SystemExit("no memberCounts found on meetup page")
    COMMUNITY.write_text(
        "# Group-level metadata surfaced in feeds (see build.py).\n"
        "# Refresh with `uv run scrape_members.py`, or by hand once we leave Meetup.\n"
        f"member_count: {m.group(1)}\n"
        f"member_count_as_of: {datetime.date.today().isoformat()}\n",
        encoding="utf-8",
    )
    print(f"member_count: {m.group(1)}")


if __name__ == "__main__":
    main()
