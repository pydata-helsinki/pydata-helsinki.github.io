#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "jinja2",
#     "pyyaml",
#     "icalendar",
# ]
# ///
"""Static site builder for pydata-helsinki.github.io.

Reads one YAML file per event from events/, renders:
  - index.html (upcoming + past event listings, prose from template)
  - events/<slug>/index.html with schema.org Event JSON-LD
  - events.ics (iCalendar), feed.xml (Atom), events.json (JSON Feed)
  - sitemap.xml
and copies static files/directories verbatim.

Usage: python build.py [--out _site]
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from icalendar import Calendar as ICalendar
from icalendar import Event as IEvent
from icalendar import vCalAddress
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
SITE_URL = "https://pydata-helsinki.github.io"
TZ = ZoneInfo("Europe/Helsinki")
DEFAULT_IMAGE = f"{SITE_URL}/assets/pydata-helsinki-banner-1200x630.webp"

ORGANIZER = {
    "@type": "Organization",
    "@id": f"{SITE_URL}/#organization",
    "name": "PyData Helsinki",
    "url": f"{SITE_URL}/",
    "sameAs": [
        "https://www.meetup.com/pydata-helsinki/",
        "https://www.linkedin.com/company/pydata-helsinki/",
        "https://fosstodon.org/@pydata_helsinki",
        "https://www.youtube.com/@PyData_Helsinki",
    ],
}

# Files and directories copied into the output as-is.
STATIC = [
    "style.css",
    "robots.txt",
    "assets",
    "slides",
    "for-speakers",
    "for-companies",
    "google4ff05d25a4ee34ed.html",
]


@dataclass
class Event:
    slug: str
    title: str
    start: datetime | None = None  # aware, Europe/Helsinki
    end: datetime | None = None
    month: str | None = None  # "YYYY-MM" for old events with unknown exact date
    status: str = "scheduled"  # scheduled | cancelled
    mode: str = "offline"  # offline | online
    venue: dict = field(default_factory=dict)
    schedule: list = field(default_factory=list)  # [{time, item}] display-only timetable
    registration: dict = field(default_factory=dict)
    sponsor: dict = field(default_factory=dict)
    joint_with: list = field(default_factory=list)
    summary: str = ""
    talks: list = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{SITE_URL}/events/{self.slug}/"

    @property
    def sort_key(self) -> str:
        if self.start:
            return self.start.isoformat()
        return self.month + "-01T00:00:00"

    @property
    def anchor(self) -> str:
        """Anchor id for index.html"""
        if self.start:
            return self.start.date().isoformat()
        return self.month

    @property
    def display_date(self) -> str:
        if self.start:
            s = self.start.strftime("%-d %B %Y")
            if (self.start.hour, self.start.minute) != (0, 0):
                s += self.start.strftime(", %H:%M")
            return s
        return datetime.strptime(self.month, "%Y-%m").strftime("%B %Y")

    @property
    def machine_date(self) -> str:
        if self.start:
            if (self.start.hour, self.start.minute) != (0, 0):
                return self.start.strftime("%Y-%m-%dT%H:%M")
            return self.start.date().isoformat()
        return self.month

    def is_upcoming(self, today: date) -> bool:
        return self.start is not None and self.start.date() >= today

    @property
    def effective_sponsor(self) -> dict:
        if self.sponsor:
            return self.sponsor
        if self.talks and self.venue.get("name"):
            return self.venue
        return {}

    def jsonld(self, upcoming: bool = False) -> dict:
        data: dict = {
            "@context": "https://schema.org",
            "@type": "Event",
            "@id": self.url,
            "name": self.title,
            "url": self.url,
            "image": DEFAULT_IMAGE,
            "eventStatus": (
                "https://schema.org/EventCancelled"
                if self.status == "cancelled"
                else "https://schema.org/EventScheduled"
            ),
            "eventAttendanceMode": (
                "https://schema.org/OnlineEventAttendanceMode"
                if self.mode == "online"
                else "https://schema.org/OfflineEventAttendanceMode"
            ),
            "organizer": ORGANIZER,
            "inLanguage": "en",
            "isAccessibleForFree": True,
        }
        if self.start:
            data["startDate"] = self.start.isoformat()
        else:
            data["startDate"] = self.month
        if self.end:
            data["endDate"] = self.end.isoformat()
        if self.summary:
            data["description"] = self.summary
        if self.mode == "online":
            data["location"] = {
                "@type": "VirtualLocation",
                "url": self.registration.get("url", self.url),
            }
        else:
            place: dict = {
                "@type": "Place",
                "name": self.venue.get("name", "Helsinki"),
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Helsinki",
                    "addressCountry": "FI",
                },
            }
            if self.venue.get("address"):
                place["address"]["streetAddress"] = self.venue["address"]
            data["location"] = place
        offer = None
        if self.registration.get("url"):
            offer = {
                "@type": "Offer",
                "url": self.registration["url"],
                "price": 0,
                "priceCurrency": "EUR",
                "availability": "https://schema.org/InStock",
            }
        elif upcoming and self.status != "cancelled":
            # RSVPs not open yet: no registration url in the YAML.
            offer = {
                "@type": "Offer",
                "url": self.url,
                "price": 0,
                "priceCurrency": "EUR",
                "availability": "https://schema.org/PreSale",
            }
        if offer:
            opens = self.registration.get("opens")
            if opens:
                offer["validFrom"] = (
                    opens.isoformat() if hasattr(opens, "isoformat") else str(opens)
                )
            data["offers"] = offer
        sponsors = []
        if self.effective_sponsor:
            sp = self.effective_sponsor
            sponsors.append({"@type": "Organization", "name": sp["name"], **(
                {"url": sp["url"]} if sp.get("url") else {}
            )})
        sponsors.append(
            {"@type": "Organization", "name": "NumFOCUS", "url": "https://numfocus.org/"}
        )
        data["sponsor"] = sponsors
        performers = [
            _person(s) for t in self.talks for s in t["speakers"]
        ]
        if performers:
            data["performer"] = performers
        sub_events = []
        for t in self.talks:
            # Google flags sub-events missing what the parent has, so inherit.
            se: dict = {
                "@type": "Event",
                "name": t["title"],
                "eventStatus": data["eventStatus"],
                "location": data["location"],
                "organizer": ORGANIZER,
                "image": DEFAULT_IMAGE,
                "inLanguage": "en",
                "isAccessibleForFree": True,
                "startDate": t["start"].isoformat() if t.get("start") else data["startDate"],
            }
            if t.get("end"):
                se["endDate"] = t["end"].isoformat()
            elif "endDate" in data:
                se["endDate"] = data["endDate"]
            if t.get("description"):
                se["description"] = t["description"]
            if "offers" in data:
                se["offers"] = data["offers"]
            if t["speakers"]:
                se["performer"] = [_person(s) for s in t["speakers"]]
            if t.get("video"):
                se["recordedIn"] = {
                    "@type": "VideoObject",
                    "name": t["title"],
                    "url": t["video"],
                }
            sub_events.append(se)
        if sub_events:
            data["subEvent"] = sub_events
        return data


def _person(s: dict) -> dict:
    return {"@type": "Person", "name": s["name"], **(
        {"url": s["url"]} if s.get("url") else {}
    )}


def _as_datetime(val) -> datetime:
    if isinstance(val, str):  # "2026-08-12 17:30" (YAML needs :ss for datetime)
        val = datetime.fromisoformat(val)
    if isinstance(val, datetime):
        return val.replace(tzinfo=TZ)
    return datetime.combine(val, datetime.min.time(), TZ)  # plain date


def load_events(events_dir: Path) -> list[Event]:
    events = []
    for path in sorted(events_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        ev = Event(slug=path.stem, **raw)
        for attr in ("start", "end"):
            val = getattr(ev, attr)
            if val is not None:
                setattr(ev, attr, _as_datetime(val))
        if ev.start is None and not ev.month:
            raise ValueError(f"{path.name}: needs either 'start' or 'month'")
        if ev.registration.get("opens"):
            ev.registration["opens"] = _as_datetime(ev.registration["opens"])
        for t in ev.talks:
            for key in ("start", "end"):
                if t.get(key):
                    t[key] = _as_datetime(t[key])
            if t.get("speaker"):
                t["speakers"] = [{"name": t["speaker"], "url": t.get("speaker_url")}]
            else:
                t.setdefault("speakers", [])
            t["speaker_names"] = " & ".join(s["name"] for s in t["speakers"])
        events.append(ev)
    events.sort(key=lambda e: e.sort_key, reverse=True)
    return events


def build_ics(events: list[Event], updated: datetime | None = None) -> bytes:
    if updated is None:
        updated = datetime.now(timezone.utc)
    elif updated.tzinfo is None:
        raise ValueError("updated must be timezone-aware")
    updated = updated.astimezone(timezone.utc)

    cal = ICalendar()
    cal.add("prodid", "-//PyData Helsinki//pydata-helsinki.github.io//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "PyData Helsinki")
    cal.add("x-wr-timezone", "Europe/Helsinki")
    for ev in events:
        if ev.start is None:
            continue  # month-precision historical events don't belong in a calendar
        ie = IEvent()
        ie.add("uid", f"{ev.slug}@pydata-helsinki.github.io")
        ie.add("summary", f"PyData Helsinki: {ev.title}")
        ie.add("dtstart", ev.start)
        ie.add("dtend", ev.end or (ev.start + timedelta(hours=3)))
        ie.add("dtstamp", updated)
        ie.add("url", ev.url)
        if ev.venue.get("name"):
            loc = ev.venue["name"]
            if ev.venue.get("address"):
                loc += ", " + ev.venue["address"]
            ie.add("location", loc)
        desc = ev.summary or ""
        if ev.talks:
            talk_lines = [
                f"- {t['speaker_names']}: {t['title']}" if t["speaker_names"]
                else f"- {t['title']}"
                for t in ev.talks
            ]
            desc = (desc + "\n\nProgramme:\n" if desc else "Programme:\n") + "\n".join(talk_lines)
        desc += f"\n\nDetails: {ev.url}"
        if ev.registration.get("url"):
            desc += f"\nRegister: {ev.registration['url']}"
        ie.add("description", desc.strip())
        organizer = vCalAddress(f"{SITE_URL}/")
        organizer.params["cn"] = "PyData Helsinki"
        ie.add("organizer", organizer)
        ie.add("status", "CANCELLED" if ev.status == "cancelled" else "CONFIRMED")
        cal.add_component(ie)
    cal.add_missing_timezones()
    return cal.to_ical()


def build_json_feed(events: list[Event]) -> str:
    items = []
    for ev in events:
        content = f"<p>{html.escape(ev.display_date)}"
        if ev.venue.get("name"):
            content += f" at {html.escape(str(ev.venue['name']))}"
        content += "</p>"
        if ev.talks:
            content += "<ul>" + "".join(
                f"<li>{html.escape(t['speaker_names'])}: "
                f"{html.escape(str(t['title']))}</li>"
                if t["speaker_names"]
                else f"<li>{html.escape(str(t['title']))}</li>"
                for t in ev.talks
            ) + "</ul>"
        item = {
            "id": ev.url,
            "url": ev.url,
            "title": f"PyData Helsinki: {ev.title}",
            "content_html": content,
        }
        if ev.start:
            item["date_published"] = ev.start.isoformat()
        if ev.registration.get("url"):
            item["external_url"] = ev.registration["url"]
        items.append(item)
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "PyData Helsinki events",
        "home_page_url": f"{SITE_URL}/",
        "feed_url": f"{SITE_URL}/events.json",
        "description": "Events of the PyData Helsinki meetup group",
        "items": items,
    }
    return json.dumps(feed, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="_site", help="output directory")
    args = parser.parse_args()

    out = (ROOT / args.out).resolve()
    if out == ROOT.resolve() or out in ROOT.resolve().parents:
        parser.error(f"--out {args.out!r} resolves to {out}, which contains the source tree")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml", "html.j2", "xml.j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(site_url=SITE_URL, default_image=DEFAULT_IMAGE)

    events = load_events(ROOT / "events")
    today = datetime.now(TZ).date()
    upcoming = sorted(
        [e for e in events if e.is_upcoming(today)], key=lambda e: e.sort_key
    )
    past = [e for e in events if not e.is_upcoming(today)]

    # Index. Upcoming events join the page's @graph so aggregators can pick up
    # all event data in one fetch; same @id as the detail pages, so no dupes.
    graph = []
    for e in upcoming:
        d = e.jsonld(upcoming=True)
        d.pop("@context")
        graph.append(d)
    (out / "index.html").write_text(
        env.get_template("index.html.j2").render(
            upcoming=upcoming,
            past=past,
            upcoming_jsonld=",\n".join(
                json.dumps(d, indent=2, ensure_ascii=False) for d in graph
            ),
        ),
        encoding="utf-8",
    )

    # Event pages
    tpl = env.get_template("event.html.j2")
    for ev in events:
        page_dir = out / "events" / ev.slug
        page_dir.mkdir(parents=True)
        up = ev.is_upcoming(today)
        jsonld = json.dumps(ev.jsonld(upcoming=up), indent=2, ensure_ascii=False)
        page_dir.joinpath("index.html").write_text(
            tpl.render(event=ev, jsonld=jsonld, is_upcoming=up),
            encoding="utf-8",
        )

    # Feeds
    now = datetime.now(timezone.utc)
    (out / "events.ics").write_bytes(build_ics(events, now))
    (out / "events.json").write_text(build_json_feed(events), encoding="utf-8")
    (out / "feed.xml").write_text(
        env.get_template("feed.xml.j2").render(events=events, updated=now),
        encoding="utf-8",
    )

    # Sitemap
    urls = [f"{SITE_URL}/", f"{SITE_URL}/for-speakers/", f"{SITE_URL}/for-companies/"]
    urls += [e.url for e in events]
    (out / "sitemap.xml").write_text(
        env.get_template("sitemap.xml.j2").render(urls=urls), encoding="utf-8"
    )

    # Static passthrough
    for name in STATIC:
        src = ROOT / name
        if not src.exists():
            print(f"warning: static item {name} not found, skipping")
            continue
        if src.is_dir():
            shutil.copytree(src, out / name)
        else:
            shutil.copy2(src, out / name)

    print(f"built {len(events)} events -> {out}")


if __name__ == "__main__":
    main()
