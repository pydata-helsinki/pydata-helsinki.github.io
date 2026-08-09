build:
    uv run build.py

serve:
    uv run -m http.server -d _site/

scrape-members:
    uv run scrape_members.py

# Create a skeleton event file, e.g. `just new-event 2026-09-15-acme`
new-event slug:
    #!/usr/bin/env bash
    set -euo pipefail
    f="events/{{slug}}.yaml"
    if [ -e "$f" ]; then echo "$f already exists" >&2; exit 1; fi
    d="$(echo "{{slug}}" | cut -c1-10)"
    cat > "$f" <<EOF
    title: Meetup at TODO
    start: $d 17:30
    end: $d 20:30
    venue:
      name: TODO
      # url: https://example.com/
      # address: Katukatu 1
    # No registration url = RSVPs not open yet (page + JSON-LD say so).
    # Uncomment when registration opens:
    # registration:
    #   url: https://www.meetup.com/pydatahelsinki/events/NNNNNNNNN/
    #   platform: Meetup
    talks: []
    EOF
    echo "created $f"
