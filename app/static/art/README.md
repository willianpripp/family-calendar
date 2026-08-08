# The pictures behind the calendar

## Whose pictures

Three levels, first match wins:

1. **`willian/` or `aline/`** — that person's own set. Their devices see it and
   nobody else does.
2. **this folder** — the shared set, seen by everyone with no set of their own,
   and by any month the person has not covered.
3. **the painting** — the last resort, so no month is ever undressed.

Who a device belongs to is decided by its tailnet address, listed in
`CAL_DEVICES` in the host's `.env`. There is no login. The **Pictures** page in
the app shows what it decided, reports the address it saw, and can override the
guess per device. That page is also the fastest way to see the whole year at a
glance and spot which months are still missing.

This folder is **bind-mounted from the host**, so a picture dropped into
`/srv/lab/calendar/app/static/art/` appears on the next page load with no
rebuild and no restart.

## Adding your own — one per month

Drop a file in the right folder, named for the month:

| Month | Filename | | Month | Filename |
|---|---|---|---|---|
| January | `month-01.…` | | July | `month-07.…` |
| February | `month-02.…` | | August | `month-08.…` |
| March | `month-03.…` | | September | `month-09.…` |
| April | `month-04.…` | | October | `month-10.…` |
| May | `month-05.…` | | November | `month-11.…` |
| June | `month-06.…` | | December | `month-12.…` |

`.jpg`, `.jpeg`, `.png`, `.webp` and `.avif` all work, and the folder decides
who sees it: `aline/month-05.jpg` is hers alone, `month-05.jpg` here is
everyone's. Commit it and `make deploy`, or copy it straight to the host for a
picture that should stay out of git (see Licensing below).

## What makes a good one

- **Landscape, and at least 1920px wide.** It is stretched to cover the whole
  window. A 740px image on a 2560px monitor is upscaled to three times its
  size and looks soft — the picture is not wrong, there just is not enough of
  it. 2400px is comfortable.
- **Busy in the corners, calm in the middle** reads best, because the calendar
  grid sits over the centre.
- **Under about 1 MB.** This is opened on a phone over the tailnet; the file
  is downloaded before anything is visible.
- The calendar is dark only, so a dark or moody picture needs no help. A very
  bright one still works, it just leans harder on the veil below.

If a picture ever fights the text, the single knob is `--surface-veil` in
`static/style.css`: higher hides more of the picture behind the calendar,
lower shows more of it.

## Licensing

The repo is private today, but **it is going public eventually** (Willian's
decision, 2026-08-08), and what goes public is the **history**, not the tree.
Deleting a picture later does not remove it; that needs `git-filter-repo` and a
force-push. So the test is applied when you commit, not when you publish:

- A photograph you took yourself is fine.
- A film still, a promotional image, or something an image search turned up
  generally is **not**, whatever the search engine implies.
- The paintings that ship as fallbacks are public domain, because the artists
  died over seventy years ago. `ATTRIBUTION.md` records which is which.

For a picture that cannot be published, the escape hatch is to keep it out of
git entirely: copy it straight to `/srv/lab/calendar/app/static/art/` on the
host and add its name to `.gitignore`. The calendar renders it identically and
it is never committed, so nothing has to be scrubbed later.
