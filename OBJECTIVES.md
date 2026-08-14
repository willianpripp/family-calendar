# Objectives

Direction for the calendar. `STATUS.md` is what is true right now; this file is
what gets built next and in what order. Same arrangement as the homelab repo.

Nothing here is committed work until Willian orders it. Items marked IDEA were
raised once and not yet ratified.

## Requested by Willian 2026-08-13, not yet ordered

He has not said which of these (or the rail below) goes first; ask before
building.

1. **Standalone reminders.** Things that are not events at an hour: to-dos and
   notices ("matricula until the 19th") that live on the calendar and remind,
   without pretending to be a scheduled appointment.
2. **Richer Telegram messages.** Today the bot sends title and time only;
   include the notes, the location, and whatever else the event carries.
3. **Bot messages in English.** The app is English; the bot still says
   "Amanha" / "Em 2 horas". Everything it sends moves to English.
4. **Nag until acknowledged.** For deadline-style items that can be done
   early: remind **every day** until someone presses OK. Architecture note:
   today's bot only *sends*; an OK button means it also *receives*
   (inline keyboard + polling or webhook), which changes the reminder loop.
   Pairs naturally with item 1.
5. **A real phone experience** (shared requirement with House Finances, and
   likely future apps). The web version is good on a monitor and clumsy on the
   phones. Possibly a separate phone-shaped UI for the same app, chosen by
   device, the same way pictures already are. Validation tooling exists
   already: Playwright's device emulation (viewport, touch, user agent) covers
   Pixel/Z Flip testing without new infrastructure.

## Next, when Willian asks

1. **The rail becomes swipeable: cinema, then concerts, then big events.**
   Raised 2026-08-08, explicitly not urgent. The rail keeps its place and size;
   arrows or a swipe move sideways through panes, `scroll-snap` plus two
   buttons, no framework. Pane one is the existing cinema rail.
   - **Concerts around Atlanta:** Ticketmaster Discovery API (free key, filters
     by city/DMA plus `classificationName=music`). A sibling module to
     `news.py`, not more branches inside it.
   - **The handful of events that matter** (Super Bowl, Grammys, Oscars,
     elections): a curated table in the repo, reviewed yearly, **no API**.
     Election day is rule-based and belongs in `holidays.py`.
   - Decide before building: should a concert be addable to the calendar in
     one click? If yes, each entry pre-fills the event form, and that link is
     the part worth designing.

## Ideas raised, not ordered

- A continuous bar for multi-day trips, instead of the title repeating in each
  cell.
- A read-only iCal feed, so Aline's phone subscribes in the app she already
  opens.
- Weather on the day cells, and countdowns to the next big thing.
- Surfacing the next few events on the homelab dashboard.

## Considered and declined

- **Syncing Aline's work Outlook calendar** (2026-08-08): she adds meetings
  manually. The analysis stays in `STATUS.md` in case it returns.

## Standing constraints (they shape any new feature)

- The database is production; test writes use disposable year-2099 events.
- No login. Identity is the device (`CAL_DEVICES`), and any feature needing
  "who did this" inherits that limit.
- The repo goes public eventually; the licensing/content gate applies at
  commit time, and secrets live only in the host `.env`.
