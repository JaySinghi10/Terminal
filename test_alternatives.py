"""The alternatives endpoint, and the ownership check under it.

    python test_alternatives.py

EVERY TEST HERE IS ONE OF TWO QUESTIONS.

FIRST: can a caller read somebody else's itinerary? The secret that guards this
endpoint ships inside the app bundle, so it establishes that a build of this app
is calling and nothing about who. The device id is the only thing standing
between one passenger's alternatives and another's, and every way of getting
past it -- a wrong device, a missing one, an unreadable store -- has to answer
no rather than answer at all.

SECOND: does a refusal look like an absence? Not-owned and not-found return the
same empty block on purpose, so this cannot be used to learn which flights a
device watches. A test that let them diverge would be pinning a leak.

Offline. No bucket, no network: the watch store and the state store are both
replaced throughout, and NO PROVIDER CALL IS POSSIBLE on any path through the
endpoint -- which is itself one of the things asserted.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api                                           # noqa: E402
import pollstate                                     # noqa: E402
import store                                         # noqa: E402

FAILURES = []
PASS = 0


def check(name, ok, detail=""):
    global PASS
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "   -> %r" % (detail,)))
    if ok:
        PASS += 1
    else:
        FAILURES.append(name)


SECRET = "test-watch-secret"
api.WATCH_SECRET = SECRET
# ── REAL UUIDs, BECAUSE THE STORE REQUIRES THEM ────────────────────────────
# _clean_device_id refuses anything that is not a UUID, which is the whole of
# why the device id is worth anything as a second factor here: it is a random
# opaque value rather than a guessable handle. A test using "device-aaa" would
# have passed through a code path no real caller can reach.
DEV = "11111111-2222-4333-8444-555555555555"
NUM, DAY = "6E6188", "2026-09-08"

BLOCK = {"searched_at": "2026-09-08T04:00:00+00:00", "days_searched": 1,
         "done": True, "max_days": 7, "origin": "BOM", "destination": "BLR",
         "next_leg": {"flight_number": "6E777"},
         "rows": [{"flight_number": "6E100", "connects": "comfortable"}]}

OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

WATCHES = [
    {"device_id": DEV, "flight_number": NUM, "flight_date": DAY, "owned": True},
    {"device_id": DEV, "flight_number": "AI999", "flight_date": DAY, "owned": False},
    {"device_id": OTHER, "flight_number": "SQ1", "flight_date": DAY, "owned": True},
]

STATE = {(NUM, DAY): {"alternatives": BLOCK},
         ("AI999", DAY): {"alternatives": BLOCK},
         ("SQ1", DAY): {"alternatives": BLOCK}}


class _Sentinel:
    pass


store._bucket = lambda: _Sentinel()
store._read_watches = lambda bucket: (list(WATCHES), 0)


def fake_read_state(num, day):
    return dict(STATE.get((num, day), {})), 0


pollstate.read_state = fake_read_state


# ── NOTHING HERE MAY REACH A PROVIDER ───────────────────────────────────────
# Not a style point. The whole claim of this endpoint is that the drawer opens
# instantly and costs nothing, and the way that claim dies quietly is somebody
# adding a "just refresh it while we are here" call. If one ever appears, this
# blows up rather than billing.
def _forbidden(*a, **k):
    raise AssertionError("the alternatives endpoint made a provider call")


api.fetch_route = _forbidden
api.fetch_flight_full = _forbidden


def get(number=NUM, date=DAY, device=DEV, secret=SECRET):
    return api.get_alternatives(number, date=date, device_id=device, x_watch_secret=secret)


print("-- the happy path --")
r = get()
check("an owned, watched, cancelled flight returns its stored block",
      r["alternatives"]["rows"][0]["flight_number"] == "6E100", r)
check("and the block is handed back whole, verdicts included",
      r["alternatives"]["next_leg"]["flight_number"] == "6E777"
      and r["alternatives"]["rows"][0]["connects"] == "comfortable", r)

print()
print("-- the secret --")
check("a wrong secret is a 404, not a 403", get(secret="wrong").status_code == 404)
check("a missing secret is the same 404", get(secret=None).status_code == 404)
check("and neither leaks the block", b"6E100" not in get(secret="wrong").body)

print()
print("-- whose flight it is --")
check("another device's flight reads as empty, not as refused",
      get(number="SQ1", device=DEV) == {"alternatives": None})
check("and the device that DOES own it can read it",
      get(number="SQ1", device=OTHER)["alternatives"] is not None)
# ── MEETING A FLIGHT IS NOT BEING ON IT ────────────────────────────────────
# Somebody at arrivals has no connection to make and no seat to rebook. The
# same rule connection_candidates applies, for the same reason.
check("a flight this device is MEETING rather than flying reads as empty",
      get(number="AI999") == {"alternatives": None})
check("an unknown device reads as empty", get(device="99999999-8888-4777-8666-555555555555") == {"alternatives": None})
check("a missing device id reads as empty", get(device=None) == {"alternatives": None})
check("an empty device id reads as empty", get(device="") == {"alternatives": None})

print()
print("-- not owned and not found are the same answer --")
check("a flight with no stored block reads exactly as an unowned one does",
      get(number=NUM, date="2026-09-09") == get(number="SQ1", device=DEV),
      (get(number=NUM, date="2026-09-09"), get(number="SQ1", device=DEV)))

print()
print("-- the date --")
# THE FORMAT ONLY. _validate_route_date refuses past dates because a route
# SEARCH cannot answer for them; this reads an object already on disk, and a
# flight cancelled yesterday is exactly the case somebody opens the drawer for.
PAST = "2020-01-01"
WATCHES.append({"device_id": DEV, "flight_number": NUM, "flight_date": PAST, "owned": True})
STATE[(NUM, PAST)] = {"alternatives": BLOCK}
check("a date in the past is read, not refused", get(date=PAST)["alternatives"] is not None)
check("a malformed date reads as empty", get(date="08-09-2026") == {"alternatives": None})
check("a missing date reads as empty", get(date=None) == {"alternatives": None})
check("a blank flight number reads as empty", get(number="  ") == {"alternatives": None})
check("the number is matched case-insensitively", get(number="6e6188")["alternatives"] is not None)

print()
print("-- when the stores cannot be read --")


def boom(*a, **k):
    raise RuntimeError("bucket down")


pollstate.read_state = boom
check("unreadable state is an empty answer, not a 500", get() == {"alternatives": None})
pollstate.read_state = fake_read_state

store._read_watches = boom
check("an unreadable watch store refuses rather than assuming ownership",
      get() == {"alternatives": None})
store._read_watches = lambda bucket: (list(WATCHES), 0)

store._bucket = lambda: None
check("no bucket configured refuses too", get() == {"alternatives": None})
store._bucket = lambda: _Sentinel()

print()
print("-- and it still works afterwards --")
check("the happy path survives every failure above", get()["alternatives"] is not None)

print("\nPASSED: %d   FAILURES: %d" % (PASS, len(FAILURES)))
sys.exit(1 if FAILURES else 0)
