# Who is looking at the calendar, worked out from the device rather than a login.
#
# The calendar is shared by default: one set of events, one set of categories,
# and the only thing that varied per person used to be which picture sits
# behind it. Private events (2026-08-15) added a second consumer of the same
# answer, and it is worth being exact about what that changed. It did NOT make
# this module a guard: a private event is one kept off the other person's
# calendar, not a secret, and the identity behind it is still a cookie on a
# device that anyone in the house can pick up. Anything that needs a real
# boundary uses gate.py, which is a different question with a different answer.
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

import gate

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
    """{key, name, source, answered, addr}. `key` is None when nobody is
    identified, which is a perfectly good answer: that viewer gets the shared
    pictures.

    `answered` is the narrower question, and the reason it exists: has this
    device ever SAID who uses it. "Shared device" is a real answer that leaves
    `key` None, so the two must not be read as the same thing, or the popup
    that asks the question would come back on every page load for the one
    device in the house that answered honestly.
    """
    addr = client_addr(request)

    # An explicit choice always wins over the guess, and survives the device
    # being re-addressed.
    chosen = request.cookies.get("cal_who", "").strip().lower()
    if chosen in PEOPLE:
        return {"key": chosen, "name": PEOPLE[chosen], "source": "chosen on this device",
                "answered": True, "addr": addr}
    if chosen == "shared":
        return {"key": None, "name": "Shared", "source": "chosen on this device",
                "answered": True, "addr": addr}

    person = _device_map().get(addr or "")
    if person:
        return {"key": person, "name": PEOPLE[person], "source": "recognised device",
                "answered": True, "addr": addr}

    return {"key": None, "name": "Shared", "source": "device not recognised",
            "answered": False, "addr": addr}


def viewer_owner(request) -> str | None:
    """Whose private events this request may see, as an owner value
    ("Willian"/"Aline"), or None for a viewer the app cannot place.

    The device answers first and the login second. The cookie (or the
    CAL_DEVICES entry behind it) is the deliberate per-device answer to "who
    uses this device", so it describes the person actually holding the thing.
    An explicit "Shared device" answer is final for the same reason: the person
    who marked the kitchen tablet shared meant it, and a funnel login left in
    that browser must not quietly put private rows back on it. The login is
    consulted only when the device has said nothing at all: it is the stronger
    credential of the two, but it is per browser profile and outlives the
    session it was typed in, which is exactly the case the cookie is better at.

    None is not a failure, it is the shared viewpoint: that viewer sees the
    calendar without anybody's private rows, which is the same calendar the
    house had before this column existed.
    """
    who = whois(request)
    if who["key"]:
        return PEOPLE[who["key"]]
    if who["answered"]:
        return None
    user = gate.session_user(request)
    if user in PEOPLE:
        return PEOPLE[user]
    return None
