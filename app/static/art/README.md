# The pictures behind the calendar

## Adding your own — one per month

Drop a file in this folder named for the month and redeploy:

| Month | Filename | | Month | Filename |
|---|---|---|---|---|
| January | `month-01.…` | | July | `month-07.…` |
| February | `month-02.…` | | August | `month-08.…` |
| March | `month-03.…` | | September | `month-09.…` |
| April | `month-04.…` | | October | `month-10.…` |
| May | `month-05.…` | | November | `month-11.…` |
| June | `month-06.…` | | December | `month-12.…` |

`.jpg`, `.jpeg`, `.png`, `.webp` and `.avif` all work. Then:

```
make deploy
```

A month with no picture of its own falls back to a public-domain painting, one
per month (see `ATTRIBUTION.md`), so the calendar is never undressed while the
set is being filled in.

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

**This repository is private**, so anything dropped in here stays between the
two of us and licensing is not a practical concern. The paintings that ship as
fallbacks happen to be public domain (the artists died over seventy years ago),
which is documented in `ATTRIBUTION.md` in case this ever changes.

If the repo is ever made public, that flips: photographs you took are fine,
film stills and image-search results generally are not. The escape hatch then
is to copy the file straight to `/srv/lab/calendar/app/static/art/` on the host
and add its name to `.gitignore`. It works identically and is never published.
