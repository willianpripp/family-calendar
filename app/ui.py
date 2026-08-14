# Which UI a device gets: desktop or phone.
#
# Option B, Willian's decision of 2026-08-14 after seeing both sketched: the
# phone gets its own purpose-built screens (templates/phone/), not a reshaped
# desktop. Same routes, same context, two template sets, and the standing rule
# in the README: every feature ships on both, tested on both.
#
# Detection is the boring, honest kind: the user agent's "Mobi" token, which
# every phone browser sends and tablets and desktops do not. It decides only
# which template renders, so being wrong costs a layout, never data — the same
# cosmetic-rigour standard as people.py. And because user agents lie and taste
# varies, a cookie overrides it in either direction (the "Desktop version" /
# "Phone version" links); "auto" forgets the choice.

COOKIE = "cal_ui"


def is_phone(request) -> bool:
    chosen = request.cookies.get(COOKIE, "").strip().lower()
    if chosen == "phone":
        return True
    if chosen == "desktop":
        return False
    return "Mobi" in request.headers.get("user-agent", "")
