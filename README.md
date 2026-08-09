# Family calendar

The household calendar for the house: month, week and upcoming views, events
with categories and colours, US and Brazilian holidays, a picture per month,
and the overlap warning that was the reason for building it (a flight and a
Guns N' Roses show booked on the same evening).

Live at **https://home.example.ts.net:8446**, tailnet only.

## Running it

The stack runs on the `lab` guest of the home Proxmox box, at
`/srv/lab/calendar`. From this repo:

```
make deploy     # rsync + docker compose up -d --build
make logs
make status
```

First time on a fresh host, before the first deploy:

```
ssh lab 'mkdir -p /srv/lab/calendar/db /srv/lab/calendar/app/static/art'
scp .env.example lab:/srv/lab/calendar/.env
ssh lab 'chmod 600 /srv/lab/calendar/.env'   # then edit: set CAL_DB_PASSWORD
```

The art directory has to exist before the first `up`, because it is bind-mounted
in; Docker would otherwise create it empty and root-owned, and every month would
fall back to a painting. `make deploy` fills it.

## Whose pictures, without a login

The calendar is shared, all of it. The only per-person thing is the background:
`static/art/willian/month-05.jpg` beats `static/art/month-05.jpg` beats the
painting. Devices are matched to people by tailnet address in `CAL_DEVICES`,
and the **Pictures** page (`/who`) shows what was decided, reports the address
it saw, and overrides it per device with a cookie. See `app/people.py` for why
Tailscale's own identity headers cannot do this job.

Either of them can change a month from the browser: the button in the bottom
right of any calendar view uploads into their own folder. `static/art` is
bind-mounted read-write for this, which is the app's only writable path, and
every upload is decoded and re-encoded by Pillow rather than stored as sent.
That is what makes it safe to accept: what lands on disk is always something
Pillow produced, at 2560px or less, with the EXIF gone.

Uploaded pictures live on the host and are not in git. `make deploy` leaves them
alone (rsync without `--delete`), but nothing backs them up.

There is **no authentication**, on purpose. The app publishes to loopback only
and `tailscale serve` puts it on port 8446 of the tailnet, where everyone is
family. Do not bind it to `0.0.0.0` and do not forward it from the router.

## The database is production

It holds the family's real schedule. No `delete from events`, and never
recreate the `db` service without checking the bind mount first. To test a
write, use a disposable event in a distant year (2099) and delete it after.

Schema is created idempotently at startup by the app, so there are no migration
files. Storage is `timestamptz`; every render converts through `CAL_TZ`
(America/New_York), because the guest itself runs UTC.

## Layout

```
app/main.py          routes, schema, event and category CRUD
app/art.py           month number to background picture
app/holidays.py      US federal + Georgia, Brasil + Rio Grande do Sul, all computed
app/news.py          TMDB client for the cinema rail
app/templates/       Jinja2, server-rendered, no JS framework
app/static/art/      the pictures, one per month (see the README there)
```

## Traps that have already cost a round each

- **A UI change does not appear.** A cached stylesheet. Static URLs carry
  `?v=<hash>` and the mount sends `Cache-Control: no-cache`; if you add a new
  static route, give it the same treatment.
- **The picture does not change with the month.** This was `hx-boost`, which
  swaps the body and leaves `<head>` alone while the image lives in a `<style>`
  block there. htmx is gone. Do not add it back.
- **The picture covers the calendar.** The two fixed pseudo-elements that paint
  it sit in the root stacking context, so `.top` and `.shell` have to be lifted
  out of it explicitly.
- **A view is clipped with no scrollbar.** The desktop layout locks page
  scrolling so the week grid can scroll internally: `main` needs its own
  `overflow-y`, and every ancestor of a scroller needs `min-height: 0`.
- **`section.items` in a Jinja template** resolves to the dict's built-in
  method, not to a key of that name. The releases key is `entries` for exactly
  this reason.
- **Times need a meridiem letter** (`6:55p`). A 19:55 flight rendered as "6:55"
  reads as morning.

## Related

The host, the reverse proxy, the backups and the dashboard live in the
`homelab` repo. This repo owns only the application.
