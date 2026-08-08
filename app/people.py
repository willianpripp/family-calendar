# Who is looking at the calendar, worked out from the device rather than a login.
#
# The calendar itself is shared: one set of events, one set of categories, no
# private entries. The only thing that varies per person is which picture sits
# behind it. That is a cosmetic preference, so it is identified with cosmetic
# rigour, not with authentication. Nothing here guards anything.
#
# Tailscale's identity headers (Tailscale-User-Login and friends) are useless
# for this and it is worth saying why, because they are the obvious first idea:
# every family device signs in as Willian's single Tailscale account (his
# decision of 2026-08-07, no separate users and no ACLs), so every request
# would identify as him, including from Aline's phone. What actually differs is
# the *node*, and every node has a stable 100.x tailnet address.
#
# So: a device map, with an explicit override for anything not in it.

import os

# Display names for the people who have their own set of pictures. A key here
# is also the name of a folder under static/art/.
PEOPLE = {
    "willian": "Willian",
    "aline": "Aline",
}


def _device_map() -> dict[str, str]:
    """CAL_DEVICES="100.101.102.1=willian,100.101.102.2=aline" -> {ip: person}.

    Read on every request rather than cached, so adding a device is an edit to
    the .env plus a restart, not a code change. Unknown person keys are ignored
    rather than raising: a typo in the .env should cost the wrong wallpaper, not
    the calendar.

    Tailnet addresses are stable for the life of a node, but a device that is
    removed and re-added gets a new one. If someone's pictures stop appearing
    after they reinstalled Tailscale, this map is the first thing to check, and
    /who reports the address the app is actually seeing.
    """
    raw = os.environ.get("CAL_DEVICES", "")
    out = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        addr, person = entry.split("=", 1)
        person = person.strip().lower()
        if person in PEOPLE:
            out[addr.strip()] = person
    return out


def client_addr(request) -> str | None:
    """The tailnet address of the device asking.

    `tailscale serve` terminates TLS and proxies to loopback, so request.client
    is always 127.0.0.1 and the real peer arrives in X-Forwarded-For. Trusting
    that header is normally a mistake, because a client can forge it; here the
    only path to the app is through serve, which overwrites it, and the worst a
    forged value could achieve is a different background image.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def whois(request) -> dict:
    """{key, name, source, addr}. `key` is None when nobody is identified, which
    is a perfectly good answer: that viewer gets the shared pictures."""
    addr = client_addr(request)

    # An explicit choice always wins over the guess, and survives the device
    # being re-addressed.
    chosen = request.cookies.get("cal_who", "").strip().lower()
    if chosen in PEOPLE:
        return {"key": chosen, "name": PEOPLE[chosen], "source": "chosen on this device", "addr": addr}
    if chosen == "shared":
        return {"key": None, "name": "Shared", "source": "chosen on this device", "addr": addr}

    person = _device_map().get(addr or "")
    if person:
        return {"key": person, "name": PEOPLE[person], "source": "recognised device", "addr": addr}

    return {"key": None, "name": "Shared", "source": "device not recognised", "addr": addr}
