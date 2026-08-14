# STATUS

**Where it stands (2026-08-14):** live, in daily use. Built 2026-08-07; split
out of `homelab`, given per-person pictures, browser uploads, Telegram
reminders, yearly repetition and the veil control on 08-08; standalone
reminders with the daily nag on 08-14. **The plan lives in `OBJECTIVES.md`**;
nothing is being built until Willian orders it.

**There is real household data in it** (a Pensacola trip, flights, a Guns N'
Roses show), so treat the database as production. See the README.

## What it does

**Reminders by Telegram** (2026-08-08, bot `@Home_nanacios_bot`): 18:00 the
evening before, and two hours ahead for timed events. Routed on the event's
owner; Both goes to both phones. Sent once per event and kind
(`reminders_sent`), re-armed by any edit, retried within a six-hour grace on
Telegram failure, and yearly events re-remind every year (`day@2027` keys).
Config is `CAL_TELEGRAM_TOKEN` + `CAL_TELEGRAM_CHATS` in the host `.env`; chat
names must equal the owner values. The loop lives in the app process and says
so at startup if unconfigured.

**Standalone reminders with a daily nag** (2026-08-14, Willian's items 1 and 4
of 08-13): a "Reminder / to-do" checkbox on the event form for things that are
owed rather than scheduled ("matricula until the 19th"). One due date, no hour.
The item sits on its due day only and never takes part in the overlap warning
in either direction: a to-do does not double-book a day. The bot nags at 09:00
every day from creation until someone presses the checkbox next to the title
(any view has it), and passing the due date does not silence it: the item turns
red, surfaces in a "Needs attention" section at the top of Upcoming, and keeps
nagging. The OK is a toggle, so a misclick is undone by one more click; edits
re-arm reminders as usual but never touch the acknowledgement. Sent-keys are
per day (`nag@2026-08-19`), the same idea as the yearly `day@2027` keys.
Yearly repetition is refused for reminders, in the form and in the handler: a
projected occurrence copies `acknowledged_at` forward, so a yearly to-do
acknowledged once would silently never nag again.

**Bot messages in English** (2026-08-14, item 3): everything the bot sends is
English now ("Tomorrow, 7:00pm", "In 2 hours", "Reminder: due by Aug 19",
"(both of you)"), same clock style as the app. A nag always opens with
"Reminder:" and scheduled kinds never do, so one line on the phone already
says which of the two it is (Willian's ask, same day). Titles stay in
whatever language they were written in.

**What "on time" means here:** a reminder may arrive up to about five minutes
after its nominal moment, the reminder loop's tick interval, by design. On
2026-08-14 that tolerance was mistaken for a dead loop mid-demo (the check
outran the tick), which is why a failed delivery now logs loudly instead of
retrying in silence, and why app-down alerting was handed to the homelab
side the same night: the loop cannot self-report its own death.

**The nag answers back** (2026-08-14, night): every nag message carries two
inline buttons. **Done** runs the same acknowledgement as the calendar's
checkbox, one direction only (un-acknowledging stays in the calendar UI, so a
mispress in chat is always visible and reversible there). **Not yet** changes
nothing on purpose, tomorrow's 09:00 nag was coming anyway; its toast is the
entire feature, telling "seen and deferred" apart from "never saw it". The
app long-polls getUpdates (`bot_loop`/`bot_tick`, offset persisted in
`bot_state` so a restart cannot replay presses) and accepts callbacks only
from the two chats in `CAL_TELEGRAM_CHATS`. Long polling is load-bearing:
Telegram expires a press's toast about 30 seconds after the finger, and the
first build polled every 60 seconds, which answered into the void and read
as "nothing happened" on the phone. Learned live.

**Richer messages** (2026-08-14, item 2): the message reads like the calendar
entry: when-line, sticker riding the title, location, notes (capped at 200
characters), category, "(both of you)" for Both. Empty fields simply do not
appear, so a bare to-do is still two lines. Colour is the one field left
behind: a plain-text Telegram message has nowhere to put it, and the sticker
plus category already carry the identity.

**The front door for the internet** (2026-08-14, evening): the calendar is on
the public internet (`https://home.example.ts.net:10000`, Tailscale
Funnel) for Aline's work MacBook, and a visitor whose real address is public
gets the app's own login page instead of the old basic_auth popup. Accounts
`willian` and `aline`; the pbkdf2 hashes and the cookie-signing secret live
only in the host `.env` (`python3 app/gate.py 'the-password'` mints a hash).
Tailnet (:8446) and home-LAN devices are never asked. The real client is read
from the right end of X-Forwarded-For, skipping the on-host proxy hops, so a
forged header cannot claim a trusted address (`app/gate.py` explains the
chain). Sessions are a 60-day HMAC cookie; a wrong password waits a second;
the wallpapers are family photos so /static/art is gated too, with only
/health and the stylesheet public. Logging in also sets whose pictures these
are, same contract as /who. calgate was retired from the homelab repo the
same evening, funnel straight to the app since.

**Yearly repetition** (same day): a checkbox on the event form, for birthdays
and anniversaries by Willian's scoping (bills live in the finances app). One
boolean, not RRULE: stored once at its first occurrence, projected into every
view at render time, Feb 29 lands on the 28th off-years, nothing repeats
backwards, and clicking an occurrence edits the series. Deleting deletes the
series.

**The veil control** (same day): the ◐ button bottom right cycles the calendar's
transparency 72 → 52 → 32 → 14 → 4 → 88 and around, per device by cookie, so
near-invisible on the monitor does not blind the phone in the sun. Fixed steps
rather than free input, so one more click always returns to readable.


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

**Backed up nightly since 2026-08-08** by the homelab repo's `service_backup`
role: the database AND the pictures (`art.tar.gz`), 07:30 UTC, restore-rehearsed
the same day. A failed run alerts both phones through the bot.

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
person folders beat the shared level beats the painting (credits in
`ATTRIBUTION.md`). Upload from the browser, or commit and `make deploy`.

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

## Considered and declined

**Syncing Aline's work Outlook calendar into this one** (2026-08-08). She asked
whether an invite could arrive here as a proposal she accepts or dismisses,
since she does not attend all of them. Technically fine: a `proposals` table, an
inbox, dedupe on the invite `UID` plus sequence, and the Telegram bot as the
prompt. The feed was the problem, not the app.

Every route out of a corporate Microsoft 365 tenant costs something she should
not have to pay: Graph API needs her IT to approve an app registration and puts
a refresh token for her work account on a mini PC at home; a published ICS link
is usually blocked and, when it is not, leaves her work calendar readable by
anyone with the URL; forwarding invites to a mailbox is what DLP exists to
block. Power Automate inside her own tenant was the least bad option.

**Willian's call, same day: she will do it manually.** Do not rebuild this
unless she asks. If it ever comes back, the notes above are the starting point,
and the two open questions were whether her employer permits it at all, and
whether meeting titles should default to "Busy" given this calendar is shared
and has no per-user login.

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
