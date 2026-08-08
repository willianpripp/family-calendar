# Holidays for the two countries this household lives between: the US (federal
# plus Georgia) and Brazil (national plus Rio Grande do Sul).
#
# Computed, never stored. A table of holidays would need maintaining every
# December and would silently run out; the movable Brazilian ones (Carnaval,
# Sexta-feira Santa, Corpus Christi) all derive from Easter, which is an
# algorithm, so nothing here has an expiry date.
#
# ONE THING NEEDS A HUMAN EYE, and it is deliberately marked in the code below:
# several Georgia state holidays are set by gubernatorial proclamation each
# year rather than by fixed rule, so the December dates in particular can shift
# by a day. What is encoded here is the usual pattern, not a guarantee. Check
# them against the state calendar the first time a year matters.

from datetime import date, timedelta
from functools import lru_cache

# Region codes, in the order they should be shown when a day carries several.
US_FEDERAL = "US"
GEORGIA = "GA"
BR_NATIONAL = "BR"
RIO_GRANDE_DO_SUL = "RS"
# Nobody gets the day off, but a family calendar that does not know when
# Mother's Day is has missed the point. Kept in its own region so it can be
# styled as what it is: a date to remember, not a public holiday.
OBSERVANCE = "OB"

REGION_LABEL = {
    US_FEDERAL: "US",
    GEORGIA: "GA",
    BR_NATIONAL: "BR",
    RIO_GRANDE_DO_SUL: "RS",
    OBSERVANCE: "Date",
}


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
def holidays_for_year(year: int) -> dict[date, list[tuple[str, str]]]:
    """{date: [(name, region), ...]} for one year, all four regions."""
    e = easter(year)
    thanksgiving = nth_weekday(year, 11, 3, 4)  # 4th Thursday

    entries: list[tuple[date, str, str]] = [
        # --- US federal ------------------------------------------------------
        (date(year, 1, 1), "New Year's Day", US_FEDERAL),
        (nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day", US_FEDERAL),
        (nth_weekday(year, 2, 0, 3), "Presidents' Day", US_FEDERAL),
        (nth_weekday(year, 5, 0, -1), "Memorial Day", US_FEDERAL),
        (date(year, 6, 19), "Juneteenth", US_FEDERAL),
        (date(year, 7, 4), "Independence Day", US_FEDERAL),
        (nth_weekday(year, 9, 0, 1), "Labor Day", US_FEDERAL),
        (nth_weekday(year, 10, 0, 2), "Columbus Day", US_FEDERAL),
        (date(year, 11, 11), "Veterans Day", US_FEDERAL),
        (thanksgiving, "Thanksgiving", US_FEDERAL),
        (date(year, 12, 25), "Christmas Day", US_FEDERAL),

        # --- Georgia ---------------------------------------------------------
        # Only the ones Georgia adds on top of the federal list. The state
        # observes the federal days too, so repeating them here would double
        # every cell.
        #
        # PROCLAIMED ANNUALLY, not fixed by rule: the April state holiday, the
        # December pair, and whether Columbus Day is swapped for a day around
        # Thanksgiving. The pattern below is the usual one; verify against the
        # state calendar before trusting a specific year.
        (nth_weekday(year, 4, 0, 4), "State Holiday (GA)", GEORGIA),
        (thanksgiving + timedelta(days=1), "State Holiday (day after Thanksgiving)", GEORGIA),
        (date(year, 12, 24), "Washington's Birthday (observed in GA)", GEORGIA),
        (date(year, 12, 26), "State Holiday (GA)", GEORGIA),

        # --- Brasil, nacional -------------------------------------------------
        (date(year, 1, 1), "Confraternizacao Universal", BR_NATIONAL),
        (e - timedelta(days=48), "Carnaval", BR_NATIONAL),
        (e - timedelta(days=47), "Carnaval", BR_NATIONAL),
        (e - timedelta(days=46), "Quarta-feira de Cinzas (ate as 14h)", BR_NATIONAL),
        (e - timedelta(days=2), "Sexta-feira Santa", BR_NATIONAL),
        (e, "Pascoa", BR_NATIONAL),
        (date(year, 4, 21), "Tiradentes", BR_NATIONAL),
        (date(year, 5, 1), "Dia do Trabalho", BR_NATIONAL),
        (e + timedelta(days=60), "Corpus Christi", BR_NATIONAL),
        (date(year, 9, 7), "Independencia do Brasil", BR_NATIONAL),
        (date(year, 10, 12), "Nossa Senhora Aparecida", BR_NATIONAL),
        (date(year, 11, 2), "Finados", BR_NATIONAL),
        (date(year, 11, 15), "Proclamacao da Republica", BR_NATIONAL),
        # National since Lei 14.759/2023; before that it was state-level only.
        (date(year, 11, 20), "Consciencia Negra", BR_NATIONAL),
        (date(year, 12, 25), "Natal", BR_NATIONAL),

        # --- Rio Grande do Sul -------------------------------------------------
        (date(year, 9, 20), "Revolucao Farroupilha (Dia do Gaucho)", RIO_GRANDE_DO_SUL),

        # --- observances, both countries ----------------------------------------
        # Mother's Day falls on the same Sunday in both; Father's Day does not,
        # which is exactly the kind of thing this row exists to stop us
        # forgetting.
        (date(year, 2, 14), "Valentine's Day", OBSERVANCE),
        (nth_weekday(year, 5, 6, 2), "Mother's Day / Dia das Maes", OBSERVANCE),
        (date(year, 6, 12), "Dia dos Namorados (BR)", OBSERVANCE),
        (nth_weekday(year, 6, 6, 3), "Father's Day (US)", OBSERVANCE),
        (nth_weekday(year, 8, 6, 2), "Dia dos Pais (BR)", OBSERVANCE),
        (date(year, 10, 31), "Halloween", OBSERVANCE),
        (date(year, 12, 24), "Christmas Eve", OBSERVANCE),
        (date(year, 12, 31), "New Year's Eve", OBSERVANCE),
    ]

    out: dict[date, list[tuple[str, str]]] = {}
    for d, name, region in entries:
        out.setdefault(d, []).append((name, region))
    return out


def holidays_between(start: date, end: date) -> dict[date, list[dict]]:
    """{date: [{name, region, label}]} for [start, end], inclusive."""
    out: dict[date, list[dict]] = {}
    for year in range(start.year, end.year + 1):
        for d, items in holidays_for_year(year).items():
            if start <= d <= end:
                out[d] = [
                    {"name": n, "region": r, "label": REGION_LABEL[r]} for n, r in items
                ]
    return out
