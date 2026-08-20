# Objectives

Direction for the calendar. `STATUS.md` is what is true right now; this file
is what gets built next and in what order.

Nothing here is committed work until it is explicitly ordered. Items marked
IDEA were raised once and not yet ratified.

## Delivered, kept here for the shape of the reasoning

- **The OK inside Telegram**, together with a "Not yet" button — see
  `STATUS.md` ("The nag answers back") for the shape and for why long
  polling is load-bearing there.
- **A real phone experience** — a separate phone-shaped UI for the same app,
  chosen by device the same way per-person pictures already are. Delivered
  in full: the event form, the pictures page and the categories page all got
  their phone screens too, so no page wears desktop chrome on a phone
  anymore.
- **App-down alerting**, delivered from outside this repo: an external
  monitor probes every household app on a short interval and pages if one
  goes quiet for several checks running, with a recovery message on the way
  back. Standing obligation on this repo: `GET /health` stays cheap and
  auth-free, because it is load-bearing for that monitor.
- **Login for visitors outside the private network** — the arrangement lives
  in `STATUS.md` and `app/gate.py`. If accounts ever grow beyond the two the
  household currently has, the hashes in the host `.env` are the only place
  to touch.

## Requested, not yet ordered

1. **A day cell must show all its events.** In the month grid a day with many
   events currently clips after a handful; the rest are invisible, which is
   the one failure a calendar must not have. Plan: the event stack inside the
   cell becomes its own scroller, so the day number stays put and a crowded
   day scrolls within its own cell rather than hiding anything.
2. **Picking a start time should carry the event's existing duration
   forward.** The form already opens with a default duration, but changing
   the start time currently leaves the end time where it was. Plan: when the
   start changes, the end follows by the same offset, keeping whatever
   duration was already on the form; an edited event keeps its length, a new
   one keeps the default. Adjusting the end by hand afterwards still works,
   it is just no longer required.
3. **The pictures page needs plainer labels.** Numeric month captions and a
   bare "1 painting" caption say nothing at a glance; captions should read as
   month names, with the fallback-painting note kept as a small aside, and
   the year grid should sit on the same surface panel the rest of the page's
   text already uses instead of fighting the background photo directly.
4. **The side rail should follow the same transparency control as the
   calendar.** Right-hand panels currently sit at a fixed opacity while the
   calendar's own transparency is cycled by its control; they should track
   the same setting the day cells do.

## Next, when ordered

1. **An authenticated create-reminder API for the finances app.** The house
   finances app (separate repo) will push reminders here: contract or
   subscription ending, card statement due, a spend-goal deadline. This repo
   grows one small `POST` endpoint that creates a reminder/to-do the same
   way the form does, guarded by a shared secret in the host `.env` (the
   private-network path has no login, so the endpoint needs its own key).
   The existing Telegram bot then delivers these like any other reminder,
   which is the point: the finances app never talks to Telegram itself.
   Design the payload once (title, due date, category, who), because the
   finances side will be built against it.
2. **The rail becomes swipeable: what's playing, then concerts, then major
   events.** Not urgent. The rail keeps its place and size; arrows or a swipe
   move sideways through panes, using scroll-snap plus two buttons, no
   framework. The existing "what's playing" rail becomes pane one.
   - **Concerts nearby:** a free ticketing-discovery API filtered by
     region and event type, as a sibling module to `app/news.py` rather than
     more branches inside it.
   - **The handful of events that matter regardless of category** (major
     sporting finals, awards shows, elections): a small curated table in the
     repo, reviewed yearly, no API. An election day is rule-based and
     belongs in `app/holidays.py` instead.
   - Decide before building: should one of these be addable to the calendar
     in a single click? If so, each entry should pre-fill the event form, and
     that link is the part worth designing carefully.

## Ideas raised, not ordered

- Real snoozing for the nags ("remind me again in a few days"): stateful,
  needs a date column and its own design. The stateless "Not yet" button is
  deliberately not this.
- A continuous bar for multi-day trips, instead of the title repeating in
  each day's cell.
- A read-only iCal feed, so a phone's own calendar app can subscribe to this
  one.
- Weather on the day cells, and countdowns to the next big thing.
- Surfacing the next few events on a household dashboard outside this repo.

## Considered and declined

- **Syncing a work calendar automatically**: the analysis stays in
  `STATUS.md` in case it returns; the decision for now is to add such events
  manually.

## Standing constraints (they shape any new feature)

- The database backing a real deployment holds a real household's schedule;
  test writes should use a disposable event far in the future and delete it
  after.
- There is no login on the private-network path. Identity there is the
  device (`CAL_DEVICES`), and any feature needing "who did this" inherits
  that limit.
- Anything published here needs to pass a plain test at commit time: would
  this be fine as public information? Secrets live only in a host `.env`,
  never in the repo.
