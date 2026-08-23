# pydata-helsinki.fi

Static site for the PyData Helsinki meetup group, deployed to Cloudflare Pages.

## Build

`just build` (= `uv run build.py`) renders everything into `_site/`:

- One YAML file per event in `events/` → `/events/<slug>/index.html` + `index.md`
  with schema.org Event JSON-LD
- `templates/*.j2` (Jinja2) → `index.html`/`index.md`, `/events/index.html`/`index.md`,
  `feed.xml`, `sitemap.xml`; each `*.html.j2` page template has a `*.md.j2` twin
- `events.ics` (iCalendar) and `events.json` (JSON Feed; fetches the deployed
  feed to keep `date_modified` stable, so the build needs network access)
- Static passthrough (the `STATIC` list in `build.py`): `for-speakers/`,
  `for-companies/`, `llms.txt`, `assets/`, `slides/`, etc.

`just new-event <slug>` scaffolds an event YAML; `community.yaml` holds the
scraped member count.

## Conventions

- Every HTML page has a markdown twin at `index.md` next to it. Generated pages
  get theirs from the `.md.j2` templates; `for-speakers/index.md` and
  `for-companies/index.md` are maintained by hand in sync with their HTML.
- `llms.txt` links the markdown pages and feeds. When adding or modifying
  content pages other than individual events, consider updating `llms.txt`.

## Vendored JS libraries

`assets/atcb.min.js` (add-to-calendar-button) and `assets/maplibre-gl.{js,css}`
are vendored copies, not CDN links. To update:

```sh
curl -sSL -o assets/atcb.min.js https://cdn.jsdelivr.net/npm/add-to-calendar-button@2
curl -sSL -o assets/maplibre-gl.js https://unpkg.com/maplibre-gl@5/dist/maplibre-gl.js
curl -sSL -o assets/maplibre-gl.css https://unpkg.com/maplibre-gl@5/dist/maplibre-gl.css
sed -i '' '/sourceMappingURL=/d' assets/atcb.min.js assets/maplibre-gl.js assets/maplibre-gl.css
```

Then record the new version numbers (from the file headers) and date in
`assets/README.md`.
