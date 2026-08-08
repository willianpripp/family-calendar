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
make deploy STACK=calendar
```

A month with no picture of its own falls back to the seasonal painting that
ships with its theme (see `ATTRIBUTION.md`), so the calendar is never
undressed while the set is being filled in.

## What makes a good one

- **Landscape, and at least 1920px wide.** It is stretched to cover the whole
  window. A 740px image on a 2560px monitor is upscaled to three times its
  size and looks soft — the picture is not wrong, there just is not enough of
  it. 2400px is comfortable.
- **Busy in the corners, calm in the middle** reads best, because the calendar
  grid sits over the centre.
- **Under about 1 MB.** This is opened on a phone over the tailnet; the file
  is downloaded before anything is visible.
- Dark or moody images work with either theme; a very bright one is better
  viewed with the calendar in light mode (the ◐ button in the header).

If a picture ever fights the text, the single knob is `--surface-veil` in
`static/style.css`: higher hides more of the picture behind the calendar,
lower shows more of it.

## Licensing, and why it matters here

**This repository is public.** Anything committed here is published. The
paintings that ship as fallbacks are all public domain — the artists died over
seventy years ago — which is why they can be. A photograph you took yourself is
fine. A film still, a promotional image, or something found through an image
search generally is **not**, whatever the search engine implies.

If you want a picture that cannot be published, keep it out of git: copy it
straight to `/srv/lab/calendar/app/static/art/` on the host and add the
filename to `.gitignore`. It will work exactly the same and will not be
redistributed.
