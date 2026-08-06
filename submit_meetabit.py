#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "jinja2",
#     "pyyaml",
#     "icalendar",
#     "requests",
# ]
# ///
"""Submit one event to Meetabit's manual event form.

Usage:
  uv run submit_meetabit.py events/2026-08-12-visma.yaml          # dry run
  MEETABIT_COOKIE='...' uv run submit_meetabit.py events/2026-08-12-visma.yaml --post

MEETABIT_COOKIE is the full Cookie request header of a logged-in browser
session (devtools > Network > any meetabit.com request > copy Cookie header).
"""

import argparse
import os
import re
import sys
from pathlib import Path

import requests

from build import ROOT, load_events

COMMUNITY = "https://www.meetabit.com/communities/pydata-helsinki"


def payload(ev) -> dict:
    desc = ev.summary or ""
    if ev.talks:
        lines = [
            f"- {t['speaker_names']}: {t['title']}" if t["speaker_names"] else f"- {t['title']}"
            for t in ev.talks
        ]
        desc += ("\n\nProgramme:\n" if desc else "Programme:\n") + "\n".join(lines)
    desc += f"\n\nDetails: {ev.url}"
    data = {
        "event[name]": ev.title,
        "event[start_date]": ev.start.strftime("%d.%m.%Y"),
        "event[start_time]": ev.start.strftime("%H:%M"),
        "event[description]": desc.strip(),
    }
    if ev.end:
        data["event[end_date]"] = ev.end.strftime("%d.%m.%Y")
        data["event[end_time]"] = ev.end.strftime("%H:%M")
    address = ", ".join(
        str(v) for v in (ev.venue.get("name"), ev.venue.get("address")) if v
    )
    if address:
        data["event[address]"] = address
    if ev.registration.get("url"):
        data["event[registration_url]"] = ev.registration["url"]
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event", help="path to event YAML (or bare slug)")
    parser.add_argument("--post", action="store_true", help="actually submit")
    args = parser.parse_args()

    slug = Path(args.event).stem
    matches = [e for e in load_events(ROOT / "events") if e.slug == slug]
    if not matches:
        sys.exit(f"no event with slug {slug!r}")
    ev = matches[0]
    if ev.start is None:
        sys.exit("event has no start datetime")

    data = payload(ev)
    for k, v in data.items():
        print(f"{k}: {v}")
    if not args.post:
        print("\ndry run — pass --post to submit")
        return

    cookie = os.environ.get("MEETABIT_COOKIE") or sys.exit("MEETABIT_COOKIE not set")
    s = requests.Session()
    s.headers["Cookie"] = cookie

    listing = s.get(COMMUNITY)
    if ev.title in listing.text:
        sys.exit(f"an event named {ev.title!r} is already listed on {COMMUNITY}")

    form = s.get(f"{COMMUNITY}/events/new")
    m = re.search(r'name="authenticity_token" value="([^"]+)"', form.text)
    if "sign_in" in form.url or not m:
        sys.exit("not logged in — MEETABIT_COOKIE is missing or expired")
    data["authenticity_token"] = m.group(1)

    resp = s.post(f"{COMMUNITY}/events", data=data, allow_redirects=False)
    if resp.status_code in (302, 303):
        print(f"\nsubmitted: {resp.headers['Location']}")
    else:
        sys.exit(f"\nsubmit failed (HTTP {resp.status_code}) — check the form fields")


if __name__ == "__main__":
    main()
