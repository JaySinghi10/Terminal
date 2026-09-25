"""The /watched endpoint, and the fresh flag on /flight.

    python test_watched.py

THREE QUESTIONS.

FIRST: does it ever reach a provider? The whole feature is that an open app can
stay current for nothing. Every provider is replaced with something that raises.

SECOND: does the age it reports tell the truth? The stored DTO says it is zero
seconds old, because it was when the poller fetched it. Served as stored, every
read would make a fourteen-minute-old copy look brand new -- and updatedAt,
computed from that age, is what decides whether a live countdown is trusted.

THIRD: does it hand one device's flights to another? Same bar as /alternatives,
with one deliberate difference: a flight somebody is MEETING is theirs to watch.

Offline. No bucket, no network.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

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
DEV = "11111111-2222-4333-8444-555555555555"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

WATCHES = [
    {"device_id": DEV, "flight_number": "KL606", "flight_date": "2026-09-23", "owned": True},
    {"device_id": DEV, "flight_number": "KL877", "flight_date": "2026-09-24", "owned": True},
    # MEETING, and still hers to read -- see watched_by_device.
    {"device_id": DEV, "flight_number": "AI1891", "flight_date": "2026-09-25", "owned": False},
    {"device_id": OTHER, "flight_number": "SQ1", "flight_date": "2026-09-24", "owned": True},
]


def dto(num):
    return {"flight_number": num, "status": "scheduled", "data_age_seconds": 0}


POLLED = datetime.now(timezone.utc) - timedelta(minutes=14)
STATE = {
    ("KL606", "2026-09-23"): {"dto": dto("KL606"), "last_adb_at": POLLED.isoformat(),
                              "landing": {"outcome": "pending"}, "last_fr24_at": POLLED.isoformat()},
    ("KL877", "2026-09-24"): {"dto": dto("KL877"), "last_adb_at": POLLED.isoformat()},
    ("AI1891", "2026-09-25"): {"dto": dto("AI1891"), "last_adb_at": POLLED.isoformat()},
    ("SQ1", "2026-09-24"): {"dto": dto("SQ1"), "last_adb_at": POLLED.isoformat()},
}


class _Sentinel:
    pass


store._bucket = lambda: _Sentinel()
store._read_watches = lambda bucket: (list(WATCHES), 0)
pollstate.read_state = lambda n, d: (dict(STATE[(n, d)]) if (n, d) in STATE else None, 0)


def _forbidden(*a, **k):
    raise AssertionError("/watched made a provider call")


api.fetch_route = _forbidden
api.fetch_flight_full = _forbidden


def get(pairs, device=DEV, secret=SECRET):
    return api.get_watched(device_id=device, f=pairs, x_watch_secret=secret)


def nums(r):
    return sorted(x["flight_number"] for x in r["flights"])


print("-- what comes back --")
r = get(["KL606:2026-09-23", "KL877:2026-09-24"])
check("the device's own flights come back, and no provider is touched",
      nums(r) == ["KL606", "KL877"], r)
check("with the stored landing, so the device need not ask FR24 itself",
      [x for x in r["flights"] if x["flight_number"] == "KL606"][0]["landing"]
      == {"outcome": "pending"})
check("and when the server last asked the provider",
      r["flights"][0]["polled_at"] == POLLED.isoformat())

print()
print("-- the age is corrected --")
age = [x for x in r["flights"] if x["flight_number"] == "KL606"][0]["dto"]["data_age_seconds"]
check("a copy polled fourteen minutes ago says it is fourteen minutes old, not zero",
      13 * 60 <= age <= 15 * 60, age)
check("and the stored object is not mutated by the correction",
      STATE[("KL606", "2026-09-23")]["dto"]["data_age_seconds"] == 0)

print()
print("-- whose flights --")
check("a flight she is MEETING is returned: status is what a meeter is watching for",
      nums(get(["AI1891:2026-09-25"])) == ["AI1891"])
check("another device's flight is omitted, not refused",
      get(["SQ1:2026-09-24"]) == {"flights": []})
check("and a mixed request returns exactly her half of it",
      nums(get(["KL606:2026-09-23", "SQ1:2026-09-24"])) == ["KL606"])
check("an unknown device gets nothing",
      get(["KL606:2026-09-23"], device="99999999-8888-4777-8666-555555555555") == {"flights": []})
check("a missing device id gets nothing", get(["KL606:2026-09-23"], device=None) == {"flights": []})

print()
print("-- the secret --")
check("a wrong secret is a 404", get(["KL606:2026-09-23"], secret="wrong").status_code == 404)
check("a missing one too", get(["KL606:2026-09-23"], secret=None).status_code == 404)

print()
print("-- malformed and oversized requests --")
check("a pair with no date is ignored", get(["KL606"]) == {"flights": []})
check("a malformed date is ignored", get(["KL606:23-09-2026"]) == {"flights": []})
check("no pairs at all is an empty answer, not an error", get([]) == {"flights": []})
many = ["KL606:2026-09-23"] * 40
check("the request is capped, so one call cannot read the bucket forty times",
      len(get(many)["flights"]) == api.WATCHED_MAX_FLIGHTS)
check("the number is matched case-insensitively", nums(get(["kl606:2026-09-23"])) == ["KL606"])

print()
print("-- a flight with no provider record yet --")
STATE[("KL877", "2026-09-24")] = {"dto": None}
check("is omitted, so the device keeps what it has", nums(get(["KL877:2026-09-24"])) == [])

print()
print("-- when the watch store cannot be read --")


def boom(*a, **k):
    raise RuntimeError("bucket down")


store._read_watches = boom
check("nothing is returned: an unreadable store is no, not yes",
      get(["KL606:2026-09-23"]) == {"flights": []})
store._read_watches = lambda bucket: (list(WATCHES), 0)

print()
print("-- /flight's fresh flag --")
calls = []


def fake_full(number, day=None, origin=None, max_age=None):
    calls.append(max_age)
    return ("", {"flight_number": number})


api.fetch_flight_full = fake_full
api._validate_route_date = lambda d, max_future=None: ("2026-09-23", None)
api.get_flight("KL606", date="2026-09-23")
api.get_flight("KL606", date="2026-09-23", fresh=True)
check("an ordinary lookup may use the cache", calls[0] is None, calls)
check("fresh=1 asks with max_age zero, which no cached answer can satisfy",
      calls[1] == timedelta(0), calls)

# ── A BELT HELD UNTIL LANDING NEVER LEAVES THE SERVER ──
# The provider can publish an arrival belt a day early; the server holds it
# until the flight has landed, and neither endpoint may hand the held copy out.
print("-- no held belt is ever served --")
HELD = "_baggage_held"
api.fetch_flight_full = lambda *a, **k: ("", {"flight_number": "KL877",
                                              "arrival": {"baggage": None, HELD: "4"}})
served = api.get_flight("KL877", date="2026-09-24")
check("/flight serves no held belt, and no belt", HELD not in served["arrival"]
      and served["arrival"]["baggage"] is None, served)
STATE[("KL877", "2026-09-24")] = {"dto": {"flight_number": "KL877", "data_age_seconds": 0,
                                          "arrival": {"baggage": None, HELD: "4"}},
                                  "last_adb_at": POLLED.isoformat()}
kl = [x for x in get(["KL877:2026-09-24"])["flights"] if x["flight_number"] == "KL877"]
check("/watched serves no held belt, and no belt",
      len(kl) == 1 and HELD not in kl[0]["dto"]["arrival"] and kl[0]["dto"]["arrival"]["baggage"] is None, kl)
check("and the stored copy keeps it for the poller to release",
      STATE[("KL877", "2026-09-24")]["dto"]["arrival"][HELD] == "4")

print("\nPASSED: %d   FAILURES: %d" % (PASS, len(FAILURES)))
sys.exit(1 if FAILURES else 0)
