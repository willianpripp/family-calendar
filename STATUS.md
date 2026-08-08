# STATUS

**Where it stands (2026-08-08):** live, in daily use, feature-complete for now.
Built 2026-08-07, reworked 08-08, split out of the `homelab` repo into its own
repo on 08-08.

**There is real household data in it** (a Pensacola trip, flights, a Guns N'
Roses show), so treat the database as production. See the README.

## NEXT SESSION: Phase 2, once the Telegram bot exists

**BLOCKED on Willian**: a bot token from `@BotFather` plus both chat IDs (each
of them messages the bot once). Then a reminder job sending to both, with lead
time per event, defaulting to one day before and again two hours before.

Two constraints that still apply. Storage is `timestamptz` and every render
goes through `CAL_TZ`, so scheduling must too. And there is no per-user
identity, so reminders route on the event's owner field (Willian / Aline /
Both), never on anything inferred.

The same bot unblocks backup failure alerts, which live in the `homelab` repo
(the `finances_backup` role). That is why the calendar was built before
off-site backup.

## What it does

Month, week and upcoming views; add, edit and delete; categories with colours;
stickers; holidays; per-month background pictures; and the overlap warning,
which **warns and offers "Save anyway" rather than blocking**, because some
overlaps are deliberate.

In the week grid, **clicking an hour** opens the form at that hour and
**dragging across hours** sets a range (6 to 8 gives 06:00 to 09:00). The hour
slots are real links, so a plain click still works with JavaScript off; the
drag only upgrades them.

The rail shows **what is at the cinema**, from TMDB. The key is installed
(`CAL_TMDB_KEY` in `/srv/lab/calendar/.env`, mode 600, gitignored). The current
month uses TMDB's curated `/movie/now_playing` for the US; other months use
that month's wide theatrical releases. That split is not incidental: asking
`/discover` about a month that has not happened yet sorts by popularity those
titles have not earned, which put a Korean comedy above Spider-Man.

The six titles are **chosen** by popularity but **ordered** by date, which are
two different jobs. Anything still to come is earliest first, which is the
order you plan in; films already showing are newest first, since "what just
opened" beats "what has been out longest".

## Whose pictures (2026-08-08)

Each of them has their own set, resolved as `art/<person>/month-NN` then
`art/month-NN` then the painting. Devices are matched to people by tailnet
address in `CAL_DEVICES` on the host, and **all five browsing devices are
mapped**: `Aline's Z Flip6` and `Alien` to her, `Pixel 10`, `Willian_PC` and
`workspace` to him. `pve` and `lab` are servers and are deliberately absent.

Tailscale's identity headers cannot do this, because every device signs in as
Willian's one account. `app/people.py` explains it at length so the idea is not
retried. The `/who` page reports the address a device actually arrived with,
which is the value `CAL_DEVICES` needs when someone reinstalls Tailscale and
gets a new one.

**Either of them can change a month from the browser** (2026-08-08): the button
in the bottom right of any calendar view, or the Pictures page for all twelve at
once. Uploads go into the uploader's own folder, are re-encoded by Pillow to
2560px JPEG with the EXIF stripped, and are cache-busted per file rather than by
the global asset hash, because a replacement keeps the same filename.

**Uploaded pictures exist only on the host** and nothing backs them up. That is
the same gap as the database: there is no backup job for `/srv/lab/calendar` at
all, which is a homelab repo task.

**Where the pictures actually are (2026-08-08):** Willian has August, October and
December in `art/willian/`, uploaded from the browser and since committed here,
which is currently their only backup. **The shared level is empty**, so every
month either of them has not covered falls straight to a painting. Aline has
none yet.

**A trap this already sprang:** Reset used to appear whenever *a* picture
existed, not when *yours* did, so clearing October while viewing as Shared
deleted the shared October for both of them. `art_for` reports the level now and
the button follows it. If a picture disappears for both of you, this is the
shape of bug to look for.

## The pictures

`app/static/art/`, named `month-01` through `month-12` (jpg/png/webp/avif),
then `make deploy`. **October and December are Willian's**; the other ten still
show a public-domain painting as a fallback, one per month, credited in
`ATTRIBUTION.md` there.

**Aim for 2560x1440**, under about a megabyte. His first attempt was 740px wide
and was upscaled 3.4x on his monitor; no setting fixes missing pixels.

**This repo is private today but is going public eventually** (Willian's
decision, 2026-08-08), and it is the git *history* that gets published. So the
licensing test applies at commit time: your own photographs yes, film stills and
image-search results no. Anything that cannot be published goes straight to the
host at `/srv/lab/calendar/app/static/art/` plus a `.gitignore` entry, and is
never committed at all. See the README in that folder.

**This file is the other thing to watch.** It names Aline and describes real
travel. Whatever the publishing mechanism turns out to be, this file needs a
pass before the repo is public.

## Deliberately removed, do not reintroduce

- **The theme engine.** It picked a picture, an accent and motifs from event
  windows. With one image per month there is nothing left for it to decide,
  and its date arithmetic was what made two months share a picture. `art.py`
  maps 1 to 12 onto a file; that is the whole rule.
- **Light mode**, the theme picker, the mode toggle, the emoji motifs.
- **Holiday regions on screen.** US federal, Georgia, Brasil and Rio Grande do
  Sul are still computed separately in `holidays.py` because the rules differ,
  but nothing says so in the UI: one colour, the name, no flags.

## Known soft spot

**Georgia's state holidays.** The April date and the December pair are set by
gubernatorial proclamation each year rather than by fixed rule. `holidays.py`
encodes the usual pattern and says so. Check them against the state calendar
before a year matters.

## The rail becomes swipeable: cinema, then concerts, then big events

Willian's idea, 2026-08-08, **explicitly not urgent**. The rail keeps its place
and its size; arrows (or a swipe) move sideways through panes. Pane one is what
is already there.

- **Concerts around Atlanta.** The realistic free source is **Ticketmaster's
  Discovery API**: a free key, generous daily limit, and it filters by city or
  DMA plus `classificationName=music`, which is exactly the query. Bandsintown
  needs partner approval and SeatGeek's free tier is thinner. Same shape as
  `news.py`, so it should be a sibling module, not more branches inside that one.
- **The handful of events that matter** (Super Bowl, Grammys, Oscars,
  elections). **Do not look for an API for these.** There are about six a year,
  the dates are announced months ahead, and every "events" API that covers them
  is paid. A curated table in the repo, reviewed once a year, is smaller,
  faster and cannot break. US federal election day is rule-based (the Tuesday
  after the first Monday in November, even years) and belongs in `holidays.py`
  alongside the rest.
- **The panes themselves** need no framework: `scroll-snap-type: x mandatory` on
  the rail with each pane a snap target, plus two arrow buttons calling
  `scrollBy`. It degrades to an ordinary scroll if the JavaScript never runs,
  which is the same bargain the week grid's drag already makes.

The one thing to decide before building: whether an interesting concert should
be **addable to the calendar in one click**. If yes, each entry needs a link
that pre-fills the event form, and that is the part worth designing rather than
bolting on.

## Ideas raised, not started

- **Recurring events.** The biggest gap: birthdays, rent and trash night all
  have to be retyped.
- A continuous bar for multi-day trips, instead of the title repeating in each
  cell.
- A read-only iCal feed, so Aline's phone subscribes in the app she already
  opens.
- Weather on the day cells, and countdowns to the next big thing.
- Surfacing the next few events on the homelab dashboard.
