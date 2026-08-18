# TODO

## Scheduled rebuild

The site is only rebuilt on a commit to `main`, but some page content is
time-dependent: an event moves from upcoming to past, and a `registration.opens`
date passing flips the page to "Register on Meetup" and bumps the event's
`date_modified` in `events.json` / `<updated>` in `feed.xml` so feed subscribers
hear about it. Until something rebuilds on a schedule, that only reaches people
when we happen to push.

Options, laziest first:

1. A GitHub Actions workflow with `on: schedule` (daily, ~06:00 Helsinki) that
   does an empty commit or calls the Cloudflare deploy hook. No new
   infrastructure; the repo has no workflows yet, so this would be the first.
2. A Cloudflare Cron Trigger on the existing worker that hits the same deploy
   hook. Keeps everything on Cloudflare, but the worker currently only serves
   assets and would grow a scheduled handler and an API token.

Either way, the build fetches the deployed `events.json` (see
`fetch_deployed_items`), so a no-op rebuild leaves `date_modified` untouched —
scheduled rebuilds don't churn the feeds.
