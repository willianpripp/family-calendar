# Holidays for the two countries this household lives between: the US (federal
# plus Georgia) and Brazil (national plus Rio Grande do Sul).
#
# The regions are still computed separately here, because that is how the rules
# differ, but they are NOT shown separately: a holiday is a holiday, it gets one
# colour, and the calendar says its name rather than which flag it belongs to.
# Willian asked for exactly that, and he is right — the household does not care
# whose holiday it is, only that the day is different.
#
# Computed, never stored. A table of holidays would need maintaining every
# December and would silently run out; the movable Brazilian ones (Carnaval,
# Sexta-feira Santa, Corpus Christi) all derive from Easter, which is an
# algorithm, so nothing here has an expiry date.
#
# ONE THING NEEDS A HUMAN EYE: several Georgia state holidays are set by
# gubernatorial proclamation each year rather than by fixed rule, so the
# December dates in particular can shift by a day. What is encoded below is the
# usual pattern, not a guarantee.

from datetime import date, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Gregorian Easter (Meeus/Jones/Butcher). Every movable Brazilian holiday
    is an offset from this date."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth <weekday> of a month, Monday=0. n=-1 means the last one."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@lru_cache(maxsize=32)
def holidays_for_year(year: int) -> dict[date, list[str]]:
    """{date: [name, ...]} for one year, every region merged together."""
    e = easter(year)
    thanksgiving = nth_weekday(year, 11, 3, 4)  # 4th Thursday

    entries: list[tuple[date, str]] = [
        # --- US federal ------------------------------------------------------
        (date(year, 1, 1), "New Year's Day"),
        (nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (nth_weekday(year, 2, 0, 3), "Presidents' Day"),
        (nth_weekday(year, 5, 0, -1), "Memorial Day"),
        (date(year, 6, 19), "Juneteenth"),
        (date(year, 7, 4), "Independence Day"),
        (nth_weekday(year, 9, 0, 1), "Labor Day"),
        (nth_weekday(year, 10, 0, 2), "Columbus Day"),
        (date(year, 11, 11), "Veterans Day"),
        (thanksgiving, "Thanksgiving"),
        (date(year, 12, 25), "Christmas Day"),

        # --- Georgia ---------------------------------------------------------
        # Only what Georgia adds on top of the federal list; the state observes
        # the federal days too, and repeating them would double every cell.
        (nth_weekday(year, 4, 0, 4), "State Holiday (Georgia)"),
        (thanksgiving + timedelta(days=1), "Day after Thanksgiving"),
        (date(year, 12, 24), "Christmas Eve holiday (Georgia)"),
        (date(year, 12, 26), "State Holiday (Georgia)"),

        # --- Brasil, nacional -------------------------------------------------
        (date(year, 1, 1), "Confraternizacao Universal"),
        (e - timedelta(days=48), "Carnaval"),
        (e - timedelta(days=47), "Carnaval"),
        (e - timedelta(days=2), "Sexta-feira Santa"),
        (e, "Pascoa"),
        (date(year, 4, 21), "Tiradentes"),
        (date(year, 5, 1), "Dia do Trabalho"),
        (e + timedelta(days=60), "Corpus Christi"),
        (date(year, 9, 7), "Independência do Brasil"),
        (date(year, 10, 12), "Nossa Senhora Aparecida"),
        (date(year, 11, 2), "Finados"),
        (date(year, 11, 15), "Proclamação da República"),
        # National since Lei 14.759/2023; before that it was state-level only.
        (date(year, 11, 20), "Consciência Negra"),
        (date(year, 12, 25), "Natal"),

        # --- Rio Grande do Sul -------------------------------------------------
        (date(year, 9, 20), "Revolução Farroupilha"),

        # --- dates worth remembering, in both countries -------------------------
        # Nobody gets the day off, but a family calendar that does not know when
        # Mother's Day is has missed the point.
        (date(year, 2, 14), "Valentine's Day"),
        (nth_weekday(year, 5, 6, 2), "Mother's Day / Dia das Mães"),
        (date(year, 6, 12), "Dia dos Namorados"),
        (nth_weekday(year, 6, 6, 3), "Father's Day"),
        (nth_weekday(year, 8, 6, 2), "Dia dos Pais"),
        (date(year, 10, 31), "Halloween"),
        (date(year, 12, 31), "New Year's Eve"),
    ]

    out: dict[date, list[str]] = {}
    for d, name in entries:
        # Same day, same name from two regions (Christmas is both countries'):
        # keep it once. Different names for the same day are both kept, since
        # "Christmas Day" and "Natal" are genuinely two things being celebrated.
        names = out.setdefault(d, [])
        if name not in names:
            names.append(name)
    return out


def holidays_between(start: date, end: date) -> dict[date, list[str]]:
    """{date: [name, ...]} for [start, end], inclusive."""
    out: dict[date, list[str]] = {}
    for year in range(start.year, end.year + 1):
        for d, names in holidays_for_year(year).items():
            if start <= d <= end:
                out[d] = names
    return out
