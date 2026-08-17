# STATUS

A running record of what was built, what was decided, and what was
deliberately left out. Newest first.

**2026-08-15, small additions:** a Visitors category, seeded at startup and
deliberately outside the "attended" set, so an in-laws' visit keeps its
reminders but never reaches another app's diary export.

**2026-08-15, field-testing round:** the first natural daily nag fired and
"Not yet" was pressed on a real phone, so every behaviour had now been
watched happen rather than only tested. Three asks came out of the morning's
observations, all shipped the same day:

- **Per-reminder lead time.** `lead_days` on a standalone reminder: null
  means nag from the moment it was created, the form proposes a week, and it
  gates the daily nag and the phone's To-dos card only — the month/week/
  upcoming chips still sit on the actual due date regardless.
- **Private events plus an identity popup.** A `private` boolean, one
  `visible_to()` SQL fragment applied by every listing query and by the
  cross-app export, and a one-tap "Who uses this device?" prompt for a device
  the app cannot yet place, whose answer is the same cookie the pictures page
  already used. A newly created Work event now proposes itself private by
  default.
- The pictures page began saying plainly, in its own wording, which level a
  new upload lands at — own, shared, or (for a device answered "Shared")
  everyone's.

**2026-08-15, photo chain audited end to end.** Verified that a picture set
from one of a person's devices reaches every other device recognised as
theirs, serving the identical file and cache-busting token; that the other
person's devices never see it; and that an unrecognised device carrying an
explicit "who am I" cookie writes into that person's own folder rather than
the shared level. The audit surfaced one honest-but-silent case: a device
answered "Shared device" has no folder of its own, so its uploads land at
the shared level for the whole household. The upload button now says so.

## What it does

**Reminders by Telegram** (2026-08-08): two per timed event, the evening
before at a fixed local hour and two hours ahead of the actual time, routed
by the event's owner field; an owner of "Both" reaches everyone. An all-day
event gets only the day-before reminder, since "two hours before" means
nothing for something with no hour. Sent once per event and kind
(`reminders_sent`), re-armed by any edit, retried within a grace window on
delivery failure, and a yearly event reminds again every year (its
sent-record is keyed by year). Configured entirely through
`CAL_TELEGRAM_TOKEN` and `CAL_TELEGRAM_CHATS`; unconfigured means the loop
simply never starts, and the app says so once at startup rather than
crashing.

**Standalone reminders with a daily nag** (2026-08-14): a "Reminder / to-do"
checkbox on the event form for things that are owed rather than scheduled —
one due date, no hour. The item never takes part in the double-booking
warning in either direction: a to-do does not double-book a day. The bot
nags once a day from creation until the checkbox next to its title is
pressed (available on every view), and passing the due date does not silence
it — the item turns red, surfaces in a "needs attention" section, and keeps
nagging. The checkbox is a toggle, so a misclick is undone with one more
click; edits re-arm reminders as usual but never touch the acknowledgement,
so fixing a typo on a finished to-do does not reopen it. Yearly repetition is
refused for reminders, in both the form and the handler: a projected
occurrence copies `acknowledged_at` forward, and a yearly to-do acknowledged
once would silently never nag again.

**Bot messages in plain English** (2026-08-14): the chrome around every
message ("Tomorrow, 7:00pm", "In 2 hours", "Reminder: due in 4 days (Aug
19)", "(both of you)") is consistent regardless of what language an event's
own title was written in. A nag always says on its first line that something
is owed and a scheduled reminder never does, so a single line on a phone's
lock screen already says which of the two kinds it is.

**The nag escalates** (2026-08-17): seven identical "due by Aug 19" messages
across a default lead window taught the eye to skip all seven. The calm days
now count down ("due in 4 days"), and the last two shout: the day before
opens "⏳ DUE TOMORROW · Aug 19" and the due day "🚨 DUE TODAY · Aug 19",
each closing with a second urgency line below the buttons' reach, so the
message reads as urgent both on the notification line and after the eye has
dropped to the bottom. Overdue keeps its single line, escalated to "🔴
OVERDUE since Aug 19". Those two days also nag twice, the second at 15:00
(`URGENT_NAG_AT`), keyed `nag-pm@<date>` so the morning send cannot suppress
it; 19:00 was rejected as already too late to act on anything.

**The phone UI** (2026-08-14, night; declared complete 2026-08-15): a
purpose-built phone experience, chosen by device and overridable by a cookie
in both directions. Bottom tabs for Today / Month / What's on / Pictures; the
home screen is today-first (open to-dos with their checkbox up top, then the
days); the month is a tap-a-day grid with colour bars; a floating add button
sits at the thumb; installable from the browser as a PWA, full-screen with
its own icon. Same routes and context as the desktop UI, a second template
set entirely. The rule that came with the decision: every new feature ships
on both UIs in the same change and is tested on both — a desktop-only feature
is not considered done. There is deliberately no phone week view; the
month's tap-a-day already covers that need.

**What "on time" means here:** a reminder may arrive up to a few minutes
after its nominal moment, the reminder loop's own tick interval, by design.
A failed delivery logs loudly rather than retrying silently, because a
missed reminder is the one failure this app exists to prevent and does not
get to be quiet about it.

**The nag answers back** (2026-08-14, night): every nag message carries two
inline buttons. Done runs the same acknowledgement as the calendar's own
checkbox, one direction only — un-acknowledging happens in the calendar UI,
so a mispress in chat is always visible and reversible there. Not Yet
changes nothing on purpose (tomorrow's nag was coming anyway); its toast is
the entire feature, telling "seen and deferred" apart from "never saw it."
The app long-polls for updates so a button press is acknowledged in a couple
of seconds rather than up to a minute later — Telegram's own "press
acknowledged" toast expires quickly, and a slow poll reads on the phone as
"nothing happened," which cost a real debugging session before the fix.

**Richer messages** (2026-08-14): the message mirrors the calendar entry
itself: a when-line, an optional sticker riding the title, location, notes
(capped in length), category, and "(both of you)" for a shared event. Empty
fields simply do not appear, so a bare to-do is still two clean lines.
Colour is the one field left behind, since a plain-text Telegram message has
nowhere to put it.

**Feeds another household app's "attended" diary** (2026-08-15): a JSON
endpoint returns every event whose category name matches a small fixed set
(cinema, concert, sports, travel, and a couple of others), matched
case-insensitively by name so a newly created category joins the feed with
zero code changes. To-dos and yearly projections are excluded on purpose, and
private rows never appear on this path at all, because the endpoint has no
viewer to be private *from* — it is read by a service both people already
read.

**Subpath-aware, so one deployment answers two ways** (2026-08-15): every
emitted URL — links, redirects, static asset paths, the PWA manifest, the
week view's own drag JavaScript — carries whatever mount prefix a
reverse proxy in front announces via `X-Forwarded-Prefix`. On the app's own
port that header is empty and every URL is plain; behind a path router
fronting a shared public host it carries something like `/calendar`, and the
manifest is generated per request so installing from that path opens back
into that path rather than the host's root.

**The front door for the public internet** (2026-08-14): a request whose
real client address is genuinely public gets the app's own login page rather
than free entry; the private network is never asked. Accounts are matched by
name, the pbkdf2 hashes and the cookie-signing secret live only in the host's
`.env`, and the real client address is read from the right-hand end of
`X-Forwarded-For`, skipping only the proxy hops this deployment actually
adds, so a forged header cannot claim a trusted address. Sessions are a
long-lived HMAC cookie; a wrong password waits a beat before responding.
Logging in also records whose pictures a session should see, the same
contract the device-recognition path uses.

**Yearly repetition** (2026-08-14): a checkbox on the event form, scoped to
birthdays and anniversaries. One boolean, not a recurrence-rule column:
stored once at its first occurrence, projected into every view at render
time, February 29th lands on the 28th in off years, nothing repeats
backwards, and clicking a projected occurrence edits the series. Deleting
deletes the series.

**The veil control:** a button cycles the calendar's own transparency through
a fixed set of steps and back around, per device via a cookie, so a setting
that reads well on a monitor does not blind a phone screen in direct
sunlight. Fixed steps rather than free input, so one more click always
returns to something readable.

Month, week and upcoming views; add, edit and delete; categories with
colours; stickers; holidays; per-month background pictures; and the overlap
warning, which **warns and offers "save anyway" rather than blocking**,
because some overlaps are deliberate.

In the week grid, clicking an hour opens the form at that hour and dragging
across hours sets a range. The hour slots are real links, so a plain click
still works with JavaScript off; dragging only upgrades them.

An optional rail can show what is currently playing at the cinema, from a
free movie-database API. Without a key configured, the rail says so plainly
and nothing else about the app changes; a dead third-party API must never be
able to take the calendar down. The current month uses that API's curated
"now playing" endpoint for a home region; other months use that month's wide
theatrical releases, because asking a discovery endpoint about a month that
has not happened yet sorts titles by a popularity score they have not earned.

## Whose pictures

Each person can have their own set, resolved as their own upload, then the
shared upload, then a public-domain painting — see `app/art.py` and the
README under `app/static/art/`. Devices are matched to people by a mapping in
`.env`; a device not in the list simply sees the shared pictures. `/who`
reports the address the app actually saw for a device, which is the value
that mapping needs.

Either person can change a month's picture from the browser: the button in
the bottom right of any calendar view, or the pictures page for all twelve at
once. Uploads are re-encoded from scratch (rotated upright, scaled down if
oversized, re-saved as JPEG), which also strips EXIF data — including,
notably, the GPS coordinates a phone photo otherwise carries.

**A trap this already sprang:** a "remove this picture" control used to
appear whenever *any* picture existed for a month, not specifically the
viewer's own, so clearing a month while viewing as "shared" deleted the
shared picture for everyone. The chain now reports which level actually
matched, and the button follows it.

## Considered and declined

**Importing a work calendar automatically.** One person's employer-hosted
calendar cannot be synced in without costing something nobody should have to
pay: a corporate API integration needs that employer's IT to approve an app
registration and puts a long-lived credential for a work account somewhere
outside their control; a published read-only feed is usually blocked by the
employer, and when it is not, leaves a work calendar readable by anyone with
the link; forwarding invites to a personal mailbox is exactly what a
company's data-loss prevention exists to catch. A same-tenant automation the
person's own account can run, entirely inside their employer's boundary, was
the least-bad option, and the decision was: do this manually rather than
build it, unless the friction of doing so becomes worse than the cost of any
of the above.

## Deliberately removed, do not reintroduce

- **The old theme engine.** It picked a picture, an accent colour and visual
  motifs from date windows around a handful of yearly events, which was
  clever and wrong: with one image per month there is nothing left for it to
  decide, and its own date arithmetic could make two different months
  collide on the same picture. `app/art.py` maps a month number onto a file;
  that is the whole rule now.
- Light mode, a theme picker, a mode toggle, emoji motifs tied to specific
  dates.
- **Holiday regions on screen.** US federal, one US state's, Brazil's
  national, and one Brazilian state's holidays are still computed separately
  in `app/holidays.py`, because the underlying rules differ, but nothing
  says so in the UI: one colour, one name, no flags, no region labels.

## Known soft spot

**One US state's holidays are set by yearly proclamation, not fixed rule**,
so a couple of the December dates in particular can shift by a day from
year to year. `app/holidays.py` encodes the usual pattern and says so in a
comment; worth checking against that state's own calendar before a year
actually matters.
