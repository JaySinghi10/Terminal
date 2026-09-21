"""The flight diagnostic.

    python test_diag.py

FOUR QUESTIONS.

FIRST: does it record what happened, and only for the flights it was asked to?
SECOND: does each delivery stage appear once, in order, with its reason?
THIRD: do the provider's values leave at six days while the skeleton stays?
FOURTH: can it ever break the thing it watches? It must never raise into a poll.

Offline. No bucket: diag and pollstate both fall back to process memory.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["DIAG_FLIGHTS"] = "KL606:2026-09-23,KL877:2026-09-24"
os.environ["DIAG_DEVICE"] = "11111111-2222-4333-8444-555555555555"

import diag                                          # noqa: E402
import pollstate                                     # noqa: E402

pollstate._bucket = lambda: None
FAILURES = []
PASS = 0


def check(name, ok, detail=""):
    global PASS
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "   -> %r" % (detail,)))
    if ok:
        PASS += 1
    else:
        FAILURES.append(name)


NOW = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
DEV = os.environ["DIAG_DEVICE"]


def doc(num="KL606", day="2026-09-23"):
    return diag._local.get(diag._key(num, day)) or {}


def events(num="KL606", day="2026-09-23", kind=None):
    return [e for e in doc(num, day).get("events", []) if kind is None or e["type"] == kind]


print("-- which flights --")
check("a named flight is watched", diag.watching("KL606", "2026-09-23"))
check("case does not matter", diag.watching("kl606", "2026-09-23"))
check("another date of the same number is not", not diag.watching("KL606", "2026-09-24"))
check("an unnamed flight is not", not diag.watching("SQ1", "2026-09-24"))
diag.note_poll("SQ1", "2026-09-24", NOW, {"tier": "near"}, [], [], [])
check("and nothing is written for it", diag._key("SQ1", "2026-09-24") not in diag._local)

print()
print("-- a poll --")
diag.note_poll("KL606", "2026-09-23", NOW,
               {"tier": "near", "adb": True, "fr24": True, "skipped": None},
               [{"field": "gate", "from": "B12", "to": "B14"}],
               [{"kind": "gate", "key": "k1", "values": {"gate": "B14"}, "deliver_after": None}],
               [{"kind": "delay", "reason": "rate floor"}])
p = events(kind="poll")[0]
check("time and tier are recorded", (p["at"], p["tier"]) == (NOW.isoformat(), "near"), p)
check("and which providers were asked", (p["adb"], p["fr24"]) == (True, True))
check("the FIELD that changed is in the skeleton", p["changed"] == ["gate"])
check("what it changed to is in values, which will expire",
      p["values"] == {"gate": {"from": "B12", "to": "B14"}})
check("the decision is recorded", events(kind="decided")[0]["kind"] == "gate")
check("and so is a decision against, with its reason",
      events(kind="decided_against")[0] == {"at": NOW.isoformat(), "type": "decided_against",
                                            "kind": "delay", "reason": "rate floor"})

print()
print("-- the delivery lifecycle --")
slot_id = "k1|" + DEV
other = "k1|99999999-8888-4777-8666-555555555555"
STATE = {"sent": {slot_id: {"sent_at": NOW.isoformat(), "ticket": "T"},
                  other: {"sent_at": NOW.isoformat(), "ticket": "U"}}}
pollstate.read_state = lambda n, d: (STATE if (n, d) == ("KL606", "2026-09-23") else None, 0)

diag.note_dispatch(NOW)
check("a send is recorded, with the kind looked up from the decision",
      [(e["type"], e["kind"]) for e in events(kind="sent")] == [("sent", "gate")])
check("and only HER slot: another device's send of the same message is not",
      len(events(kind="sent")) == 1)

diag.note_dispatch(NOW + timedelta(minutes=1))
check("a stage already seen is not recorded again on the next pass",
      len(events(kind="sent")) == 1)

STATE["sent"][slot_id]["receipt_status"] = "ok"
diag.note_dispatch(NOW + timedelta(minutes=15))
check("the receipt comes in as delivered", len(events(kind="delivered")) == 1)

STATE["sent"]["k2|" + DEV] = {"gave_up": True, "drop_reason": "stale", "kind": "delay"}
diag.note_dispatch(NOW + timedelta(minutes=16))
d = events(kind="dropped")
check("a drop is recorded with its reason",
      [(e["kind"], e["reason"]) for e in d] == [("delay", "stale")], d)

STATE["sent"]["k3|" + DEV] = {"sent_at": NOW.isoformat(), "receipt_status": "error",
                              "receipt_error": "DeviceNotRegistered"}
diag.note_dispatch(NOW + timedelta(minutes=17))
nd = events(kind="not_delivered")
check("a failed receipt says why", nd and nd[0]["reason"] == "DeviceNotRegistered", nd)

STATE["sent"]["k4|" + DEV] = {"send_error": "MessageRateExceeded", "claimed_at": None}
diag.note_dispatch(NOW + timedelta(minutes=18))
sf = events(kind="send_failed")
check("a transient send failure is recorded, and its reason",
      sf and sf[0]["reason"] == "MessageRateExceeded", sf)

print()
print("-- retention --")
before = len(events())
diag.sweep(NOW + timedelta(days=5, hours=23))
check("at five days the values are all still there",
      all("values" in e for e in events() if e["type"] in ("poll", "decided")))
diag.sweep(NOW + timedelta(days=6, hours=1))
check("past six days every provider value is gone",
      not any("values" in e for e in events()), [e for e in events() if "values" in e])
check("and each stripped event says so", events(kind="poll")[0].get("values_stripped") is True)
check("while the skeleton is untouched: same events, same fields changed",
      len(events()) == before and events(kind="poll")[0]["changed"] == ["gate"])
check("and the delivery record keeps its reasons",
      events(kind="dropped")[0]["reason"] == "stale")
diag.sweep(NOW + timedelta(days=29))
check("at twenty-nine days it is still there for review", doc() != {})
diag.sweep(NOW + timedelta(days=31))
check("and at thirty-one it is gone", doc() == {})

print()
print("-- it never breaks a poll --")


def boom(*a, **k):
    raise RuntimeError("bucket down")


pollstate.read_state = boom
real_mutate = diag._mutate
diag._mutate = boom
try:
    diag.note_poll("KL606", "2026-09-23", NOW, {"tier": "near"}, [], [], [])
    diag.note_dispatch(NOW)
    check("a storage failure inside either hook is swallowed", True)
except Exception as exc:  # noqa: BLE001
    check("a storage failure inside either hook is swallowed", False, exc)
diag._mutate = real_mutate

print()
print("-- the targets come from the environment, live --")
os.environ["DIAG_FLIGHTS"] = ""
check("clearing DIAG_FLIGHTS stops it with no code change", not diag.watching("KL606", "2026-09-23"))

print("\nPASSED: %d   FAILURES: %d" % (PASS, len(FAILURES)))
sys.exit(1 if FAILURES else 0)
