"""The connection search, offline.

    python test_connections.py

The provider is two fakes: route lists through mcp_server._adb_get, boards
through mcp_server._fetch_board. The airports are synthetic, so every distance,
country and time is chosen by the test and every assertion is exact:

    AAA (0,0) --- HAA (0,5) --- BBB (0,10)     on the line, ratio 1.0
                  HBB (0.4,4)                  a small dogleg
                  HCC (0.8,6)                  a small dogleg
                  FAR (10,5)                   ratio 2.2, pruned
                  HIN (0,4)  in another country
                  HUN (0,6)  country unknown
"""
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import connections as C     # noqa: E402
import mcp_server as M      # noqa: E402

FAILURES = []
PASS = 0


def check(name, ok, detail=""):
    global PASS
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "   -> %r" % (detail,)))
    if ok:
        PASS += 1
    else:
        FAILURES.append(name)


GEO = {
    "AAA": (0.0, 0.0, "XX"), "BBB": (0.0, 10.0, "XX"),
    "HAA": (0.0, 5.0, "XX"), "HBB": (0.4, 4.0, "XX"), "HCC": (0.8, 6.0, "XX"),
    "FAR": (10.0, 5.0, "XX"), "HIN": (0.0, 4.0, "YY"), "HUN": (0.0, 6.0, None),
}
C.AIRPORT_GEO = GEO
C._bucket = lambda: None
M._adb_configured = lambda: True
M._store_bucket = lambda: None       # boards live in memory only unless a test says so
REAL_FETCH_BOARD = M._fetch_board

LISTS = {}      # code -> [(iata, daily)]
BOARDS = {}     # (code, day) -> rows
CALLS = []      # every provider call, in order


class _Resp:
    def __init__(self, body):
        self.status_code = 200
        self._body = body
        self.content = b"x"

    def json(self):
        return self._body


def fake_adb_get(path, params=None):
    code = path.split("/")[3]
    CALLS.append(("list", code))
    return _Resp([{"destination": {"iata": i, "countryCode": None}, "averageDailyFlights": n}
                  for i, n in LISTS.get(code, [])])


IN_FLIGHT = [0, 0]      # now, most at once
_lock = threading.Lock()
BOARD_DELAY = [0.0]


def fake_fetch_board(code, day=None):
    with _lock:
        CALLS.append(("board", code, day))
        IN_FLIGHT[0] += 1
        IN_FLIGHT[1] = max(IN_FLIGHT[1], IN_FLIGHT[0])
    if BOARD_DELAY[0]:
        time.sleep(BOARD_DELAY[0])
    rows = BOARDS.get((code, day), [])
    M._ROUTE_CACHE[(code, day)] = (datetime.now(timezone.utc), rows)
    with _lock:
        IN_FLIGHT[0] -= 1
    return rows, 0, False


M._adb_get = fake_adb_get
M._fetch_board = fake_fetch_board

DAY0 = (datetime.now(timezone.utc) + timedelta(days=3)).date()
D0 = DAY0.isoformat()
D1 = (DAY0 + timedelta(days=1)).isoformat()


def at(day, hh, mm=0):
    y, m, d = map(int, day.split("-"))
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def row(fn, o, d, dep, arr):
    return {
        "flight_number": fn, "airline": None, "origin_iata": o,
        "destination_iata": d, "destination_airport": None,
        "departure_scheduled": "x", "departure_scheduled_iso": dep.isoformat(timespec="minutes"),
        "departure_timezone": "UTC",
        "arrival_scheduled": "y", "arrival_scheduled_iso": arr.isoformat(timespec="minutes"),
        "arrival_timezone": "UTC", "status": "scheduled", "departure_live": False,
        "_dep_utc": dep, "_raw_status": "",
    }


def reset():
    M._ROUTE_CACHE.clear()
    C._RESULTS.clear()
    C._local_lists.clear()
    LISTS.clear()
    BOARDS.clear()
    CALLS.clear()
    C.UNIT_CEILING = 100
    C.PARALLEL_BOARDS = 3
    IN_FLIGHT[0] = IN_FLIGHT[1] = 0
    BOARD_DELAY[0] = 0.0


def board_calls():
    return [c for c in CALLS if c[0] == "board"]


# ── THE INTERSECTION, THE PRUNE, THE RANK ───────────────────────────────────
print("-- the intersection, the detour prune and the rank --")
reset()
LISTS["AAA"] = [("HAA", 10), ("HBB", 30), ("HCC", 5), ("FAR", 99), ("ZZZ", 50)]
LISTS["BBB"] = [("HAA", 20), ("HBB", 2), ("HCC", 8), ("FAR", 99), ("QQQ", 9)]
r = C.search("AAA", "BBB", D0)
hubs = r["hubs"]
check("only airports on both lists are candidates", hubs["candidates"] == 4, hubs)
check("the hub 2.2x out of the way is pruned before any board", hubs["pruned_by_detour"] == ["FAR"], hubs)
check("ranked by the THINNER leg: HAA min(10,20)=10, HCC 5, HBB 2",
      hubs["ranked"] == ["HAA", "HCC", "HBB"], hubs["ranked"])
check("no first legs, so no hub board is fetched",
      [c for c in board_calls() if c[1] != "AAA"] == [], board_calls())
check("an empty answer is complete, with no error", r["complete"] is True and r["error"] is None and r["itineraries"] == [], r)
check("cold: two route lists and one dated origin board = 16 units", r["units_spent"] == 16, r["units_spent"])

# ── LAYOVER MINIMUMS AND THE MAXIMUM ────────────────────────────────────────
print()
print("-- the layover minimums, domestic 60 and international 120, and the 24h maximum --")


def one_hub(hub, leg1_arr, leg2_deps, ceiling=60):
    reset()
    C.UNIT_CEILING = ceiling
    LISTS["AAA"] = [(hub, 10)]
    LISTS["BBB"] = [(hub, 10)]
    BOARDS[("AAA", D0)] = [row("AA100", "AAA", hub, at(D0, 8), leg1_arr)]
    rows = []
    for i, dep in enumerate(leg2_deps):
        rows.append(row(f"AA{200 + i}", hub, "BBB", dep, dep + timedelta(hours=1)))
    day = leg2_deps[0].date().isoformat() if leg2_deps else D0
    BOARDS[(hub, day)] = rows
    return C.search("AAA", "BBB", D0)


r = one_hub("HAA", at(D0, 10), [at(D0, 10, 59)])
check("domestic: 59 minutes is not a connection", r["itineraries"] == [], r["itineraries"])
r = one_hub("HAA", at(D0, 10), [at(D0, 11, 0)])
check("domestic: 60 minutes is", len(r["itineraries"]) == 1 and r["itineraries"][0]["international"] is False, r["itineraries"])
r = one_hub("HIN", at(D0, 10), [at(D0, 11, 59)])
check("across a border: 119 minutes is not", r["itineraries"] == [], r["itineraries"])
r = one_hub("HIN", at(D0, 10), [at(D0, 12, 0)])
check("across a border: 120 is, and says international",
      len(r["itineraries"]) == 1 and r["itineraries"][0]["international"] is True, r["itineraries"])
r = one_hub("HUN", at(D0, 10), [at(D0, 11, 30)])
check("an unknown country is international: 90 minutes is refused", r["itineraries"] == [], r["itineraries"])
r = one_hub("HAA", at(D0, 10), [at(D1, 10, 1)])
check("24 hours and a minute is refused", r["itineraries"] == [], r["itineraries"])
r = one_hub("HAA", at(D0, 22), [at(D1, 6)])
check("a second leg the next local day is overnight",
      len(r["itineraries"]) == 1 and r["itineraries"][0]["overnight"] is True, r["itineraries"])

# ── THE SHAPE ───────────────────────────────────────────────────────────────
print()
print("-- the RouteItinerary shape, and the transfer label on every row --")
r = one_hub("HAA", at(D0, 10), [at(D0, 11, 0)])
it = r["itineraries"][0]
check("kind, two legs in order, hub, flags", it["kind"] == "via" and it["hub"] == "HAA"
      and [l["flight_number"] for l in it["legs"]] == ["AA100", "AA200"]
      and set(it) == {"kind", "legs", "hub", "overnight", "international", "transfer"}, it)
check("the legs are wire rows: private instants stripped, departed decided",
      not any(k.startswith("_") for l in it["legs"] for k in l) and all("departed" in l for l in it["legs"]), it["legs"][0])
check("the same carrier on both legs is 'same_carrier', not silent", it["transfer"] == "same_carrier", it)
reset()
LISTS["AAA"] = [("HAA", 10)]
LISTS["BBB"] = [("HAA", 10)]
BOARDS[("AAA", D0)] = [row("6E100", "AAA", "HAA", at(D0, 8), at(D0, 10))]
BOARDS[("HAA", D0)] = [row("AI200", "HAA", "BBB", at(D0, 12), at(D0, 13))]
check("two carriers is 'self'", C.search("AAA", "BBB", D0)["itineraries"][0]["transfer"] == "self")

# ── THE BOUND ───────────────────────────────────────────────────────────────
print()
print("-- every hub is examined, and a hub-day is skipped only when it provably cannot win --")


def bound_case(parallel):
    reset()
    C.PARALLEL_BOARDS = parallel
    LISTS["AAA"] = [("HAA", 30), ("HBB", 20), ("HCC", 10)]
    LISTS["BBB"] = [("HAA", 30), ("HBB", 20), ("HCC", 10)]
    BOARDS[("AAA", D0)] = [
        row("AA100", "AAA", "HAA", at(D0, 8), at(D0, 9)),     # fast: lands 09:00
        row("AA110", "AAA", "HBB", at(D0, 8), at(D0, 14)),    # its bound: 14:00+60m+... >= best
        row("AA120", "AAA", "HCC", at(D0, 8), at(D0, 9)),     # could still win: must be fetched
    ]
    BOARDS[("HAA", D0)] = [row("AA200", "HAA", "BBB", at(D0, 10), at(D0, 12))]   # journey 4h
    BOARDS[("HCC", D0)] = [row("AA210", "HCC", "BBB", at(D0, 10, 5), at(D0, 11, 30))]  # 3h30, the fastest
    return C.search("AAA", "BBB", D0)


print("   one board at a time, where the bound can act between every board:")
r = bound_case(1)
fetched = [c[1] for c in board_calls()]
check("HCC, lowest ranked, is still fetched because its bound is under the best", "HCC" in fetched, fetched)
check("HBB's first leg lands too late to win: bounded out, never fetched",
      "HBB" not in fetched and f"HBB {D0}" in r["hubs"]["bounded_out"], r["hubs"])
check("the next day at HAA is bounded out after its own day found a result",
      f"HAA {D1}" in r["hubs"]["bounded_out"] and ("HAA", D1) not in [c[1:] for c in board_calls()], r["hubs"])
check("the fastest is first, from the lowest-ranked hub",
      r["itineraries"][0]["hub"] == "HCC", [i["hub"] for i in r["itineraries"]])
check("complete: every hub-day was fetched or bounded out", r["complete"] is True and r["unchecked"] == [], r)
print("   three at a time, where a board may go out before the result that would rule it out:")
r3 = bound_case(3)
check("the same fastest journey", r3["itineraries"][0]["hub"] == "HCC"
      and r3["itineraries"][0]["legs"][1]["flight_number"] == "AA210", [i["hub"] for i in r3["itineraries"]])
check("and still complete", r3["complete"] is True, r3)
check("the next-day boards, sent last, are still bounded out",
      all(f"{h} {D1}" in r3["hubs"]["bounded_out"] for h in ("HAA", "HCC")), r3["hubs"])

print()
print("-- the sliding window: boards overlap, never more than PARALLEL_BOARDS at once --")
reset()
BOARD_DELAY[0] = 0.05
hubs5 = [("HAA", 50), ("HBB", 40), ("HCC", 30), ("HIN", 20), ("HUN", 10)]
LISTS["AAA"] = hubs5
LISTS["BBB"] = hubs5
BOARDS[("AAA", D0)] = [row(f"AA1{i}", "AAA", h, at(D0, 8), at(D0, 9)) for i, (h, _n) in enumerate(hubs5)]
for i, (h, _n) in enumerate(hubs5):
    BOARDS[(h, D0)] = [row(f"AA2{i}", h, "BBB", at(D0, 12), at(D0, 13))]
r = C.search("AAA", "BBB", D0)
check(f"at most {C.PARALLEL_BOARDS} boards in flight, and more than one (saw {IN_FLIGHT[1]})",
      1 < IN_FLIGHT[1] <= C.PARALLEL_BOARDS, IN_FLIGHT)
check("every first-day hub board was fetched", all(("board", h, D0) in CALLS for h, _n in hubs5), CALLS)

print()
print("-- the stream: a hub's itineraries as each board lands, the whole answer last --")
reset()
LISTS["AAA"] = [("HAA", 30), ("HCC", 10)]
LISTS["BBB"] = [("HAA", 30), ("HCC", 10)]
BOARDS[("AAA", D0)] = [row("AA100", "AAA", "HAA", at(D0, 8), at(D0, 9)),
                       row("AA120", "AAA", "HCC", at(D0, 8), at(D0, 9))]
BOARDS[("HAA", D0)] = [row("AA200", "HAA", "BBB", at(D0, 12), at(D0, 13))]
BOARDS[("HCC", D0)] = [row("AA210", "HCC", "BBB", at(D0, 11), at(D0, 12))]
events = list(C.search_events("AAA", "BBB", D0))
kinds = [e["type"] for e in events]
check("hub events, then exactly one done, last", kinds[-1] == "done" and kinds.count("done") == 1
      and set(kinds[:-1]) == {"hub"} and len(kinds) >= 3, kinds)
check("each hub event carries that hub's itineraries in the wire shape",
      all(e["itineraries"] and all(i["hub"] == e["hub"] and i["kind"] == "via" for i in e["itineraries"])
          for e in events[:-1]), events[:-1])
C._RESULTS.clear()
M._ROUTE_CACHE.clear()
whole = C.search("AAA", "BBB", D0)
# THE ITINERARIES AND THE VERDICT, not the order hub-days were logged in: boards
# land in parallel, so `checked` lists them in whatever order they finished.
check("search() gives the same answer as the stream's done event",
      events[-1]["itineraries"] == whole["itineraries"] and events[-1]["complete"] == whole["complete"]
      and sorted(events[-1]["hubs"]["checked"]) == sorted(whole["hubs"]["checked"]), whole)
reset()
events = list(C.search_events("AAA", "AAA", D0))
check("a refusal is a single done carrying the error", len(events) == 1 and events[0]["type"] == "done"
      and events[0]["error"], events)

# ── THE RUNAWAY GUARD ───────────────────────────────────────────────────────
print()
print("-- the unit guard names what it did not check, and the answer is not complete --")
check("the guard is 100 units", C.UNIT_CEILING == 100)
reset()
C.UNIT_CEILING = 20        # 12 for the lists, 4 for the origin board, one hub board
LISTS["AAA"] = [("HAA", 30), ("HCC", 10)]
LISTS["BBB"] = [("HAA", 30), ("HCC", 10)]
BOARDS[("AAA", D0)] = [
    row("AA100", "AAA", "HAA", at(D0, 8), at(D0, 9)),
    row("AA120", "AAA", "HCC", at(D0, 8), at(D0, 9)),
]
BOARDS[("HAA", D0)] = [row("AA200", "HAA", "BBB", at(D0, 16), at(D0, 17))]   # slow: 9h
BOARDS[("HCC", D0)] = [row("AA210", "HCC", "BBB", at(D0, 10, 5), at(D0, 11))]
r = C.search("AAA", "BBB", D0)
check("the guard stops at the ceiling", r["units_spent"] <= 20, r["units_spent"])
check("the unfetched hub-day is named", f"HCC {D0}" in r["unchecked"], r["unchecked"])
check("and the answer is marked incomplete, so nothing may be called fastest", r["complete"] is False, r)
check("an incomplete answer is not cached", ("AAA", "BBB", D0) not in C._RESULTS)

# ── CODESHARES ──────────────────────────────────────────────────────────────
print()
print("-- codeshares: same instants and airports are one journey --")


def codeshare(leg1_fn, leg2_fns):
    reset()
    LISTS["AAA"] = [("HAA", 10)]
    LISTS["BBB"] = [("HAA", 10)]
    BOARDS[("AAA", D0)] = [row(leg1_fn, "AAA", "HAA", at(D0, 8), at(D0, 9))]
    BOARDS[("HAA", D0)] = [row(fn, "HAA", "BBB", at(D0, 11), at(D0, 12)) for fn in leg2_fns]
    return C.search("AAA", "BBB", D0)["itineraries"]


its = codeshare("AA100", ["ZZ200", "AA300"])
check("one row, and the carrier matching the first leg wins",
      len(its) == 1 and its[0]["legs"][1]["flight_number"] == "AA300", [i["legs"][1]["flight_number"] for i in its])
its = codeshare("XX100", ["ZZ200", "YY200"])
check("no match: the alphabetically first, for stability", len(its) == 1 and its[0]["legs"][1]["flight_number"] == "YY200",
      [i["legs"][1]["flight_number"] for i in its])
reset()
LISTS["AAA"] = [("HAA", 10)]
LISTS["BBB"] = [("HAA", 10)]
BOARDS[("AAA", D0)] = [row("ZZ100", "AAA", "HAA", at(D0, 8), at(D0, 9)),
                       row("BB100", "AAA", "HAA", at(D0, 8), at(D0, 9))]
BOARDS[("HAA", D0)] = [row("BB200", "HAA", "BBB", at(D0, 11), at(D0, 12))]
its = C.search("AAA", "BBB", D0)["itineraries"]
check("a codeshared FIRST leg collapses too, to the one matching the second",
      len(its) == 1 and its[0]["legs"][0]["flight_number"] == "BB100", [i["legs"][0]["flight_number"] for i in its])

# ── ONE STOP, AND FLIGHTS THAT HAVE LEFT ────────────────────────────────────
print()
print("-- one stop only, and no first leg that has already left --")
check("every itinerary has exactly two legs and one hub",
      all(len(i["legs"]) == 2 and isinstance(i["hub"], str) for i in its))
reset()
now = datetime.now(timezone.utc)
LISTS["AAA"] = [("HAA", 10)]
LISTS["BBB"] = [("HAA", 10)]
BOARDS[("AAA", None)] = [
    row("AA100", "AAA", "HAA", now - timedelta(minutes=5), now + timedelta(hours=1)),
    row("AA101", "AAA", "HAA", now + timedelta(hours=1), now + timedelta(hours=2)),
]
today = (now + timedelta(hours=1)).date().isoformat()
BOARDS[("HAA", today)] = [row("AA200", "HAA", "BBB", now + timedelta(hours=4), now + timedelta(hours=5))]
BOARDS[("HAA", (now + timedelta(hours=1)).date().isoformat())] = BOARDS[("HAA", today)]
r = C.search("AAA", "BBB", None)
check("the rolling search drops the first leg that left five minutes ago",
      [i["legs"][0]["flight_number"] for i in r["itineraries"]] == ["AA101"], [i["legs"][0]["flight_number"] for i in r["itineraries"]])
check("a rolling origin board costs 2, not 4", r["units_spent"] == 12 + 2 + 4 or r["units_spent"] == 12 + 2 + 8, r["units_spent"])

# ── THE SPACING ─────────────────────────────────────────────────────────────
print()
print("-- the rate gate: four starts a second on the direct plan, 1.3s apart on RapidAPI --")
clock = [100.0]
waits = []
M._gate_clock = lambda: clock[0]


def fake_gate_sleep(sec):
    waits.append(round(sec, 3))
    clock[0] += sec


M._gate_sleep = fake_gate_sleep
real_gateway = M.active_gateway
M.active_gateway = lambda: "direct"
M._GATE_NEXT = 0.0
starts = []
for _ in range(9):
    M._rate_gate()
    starts.append(round(clock[0] - 100.0, 3))
check("the plan's limit and the margin under it", (M.ADB_DIRECT_REQUESTS_PER_SECOND, M.ADB_SAFE_REQUESTS_PER_SECOND) == (5, 4))
check("starts a quarter-second apart", starts == [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0], starts)
check("never more than four starts inside any one second",
      all(sum(1 for t in starts if a <= t < a + 1.0) <= 4 for a in starts), starts)
M.active_gateway = lambda: "rapidapi"
M._GATE_NEXT = 0.0
clock[0] = 200.0
waits.clear()
M._rate_gate()
M._rate_gate()
check("RapidAPI keeps the measured 1.3s", waits == [1.3], waits)
M.active_gateway = real_gateway
M._gate_clock = time.monotonic
M._gate_sleep = time.sleep
M._GATE_NEXT = 0.0

r = one_hub("HAA", at(D0, 10), [at(D0, 11, 0)])
provider = len(CALLS)

# ── THE CACHES ──────────────────────────────────────────────────────────────
print()
print("-- the route list: six days, then deleted; the assembled answer: four hours --")
r2 = C.search("AAA", "BBB", D0)
check("the same search again is served whole, for 0 units and no calls", r2["units_spent"] == 0 and len(CALLS) == provider, r2["units_spent"])
C._RESULTS.clear()
M._ROUTE_CACHE.clear()
CALLS.clear()
r3 = C.search("AAA", "BBB", D0)
check("route lists are not refetched inside six days", [c for c in CALLS if c[0] == "list"] == [], CALLS)
for key in list(C._local_lists):
    C._local_lists[key]["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=5, hours=23)).isoformat()
C._RESULTS.clear()
CALLS.clear()
C.search("AAA", "BBB", D0)
check("five days twenty-three hours: still served", [c for c in CALLS if c[0] == "list"] == [], CALLS)
for key in list(C._local_lists):
    C._local_lists[key]["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
C._RESULTS.clear()
CALLS.clear()
held = dict(C._local_lists)
C._read_list("AAA", datetime.now(timezone.utc))
check("six days: the entry is DELETED on read, not just ignored", C._list_key("AAA") not in C._local_lists, list(C._local_lists))
C._local_lists.update(held)
C.search("AAA", "BBB", D0)
check("and both lists are fetched again", sorted(c[1] for c in CALLS if c[0] == "list") == ["AAA", "BBB"], CALLS)
check("the ceiling constant is six days and not seven", C.ROUTE_LIST_CACHE_TTL == timedelta(days=6))

# ── REFUSALS ────────────────────────────────────────────────────────────────
print()
print("-- refusals cost nothing --")
reset()
check("same airport", C.search("AAA", "AAA", D0)["error"] is not None and CALLS == [])
check("not a code", C.search("AAAA", "BBB", D0)["error"] is not None and CALLS == [])
check("an airport with no known position", C.search("AAA", "QQQ", D0)["error"] is not None and CALLS == [])
check("a past date", C.search("AAA", "BBB", "2020-01-01")["error"] is not None and CALLS == [])


# ── THE BOARD CACHE IN THE BUCKET ───────────────────────────────────────────
print()
print("-- boards in the bucket: shared by every instance, inside the seven days --")


class _Blob:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def upload_from_string(self, data, content_type=None):
        self.store[self.key] = data if isinstance(data, bytes) else data.encode("utf-8")

    def download_as_bytes(self):
        return self.store[self.key]


class _Bucket:
    def __init__(self):
        self.store = {}

    def get_blob(self, key):
        return _Blob(self.store, key) if key in self.store else None

    def blob(self, key):
        return _Blob(self.store, key)


bucket = _Bucket()
M._store_bucket = lambda: bucket
window_calls = []
dep = at(D0, 9)


def fake_window(code, day, start, end):
    window_calls.append((code, day, start))
    return [row("AA900", code, "BBB", dep, dep + timedelta(hours=1))] if start == "00:00" else []


real_window = M._fetch_board_window
real_gateway = M.active_gateway
M._fetch_board_window = fake_window
M.active_gateway = lambda: "direct"
M._fetch_board = REAL_FETCH_BOARD
M._ROUTE_CACHE.clear()
rows, age, hit = M._fetch_board("HAA", D0)
check("a cold board is fetched: both windows, and not a cache hit", len(window_calls) == 2 and hit is False, window_calls)
check("and written to the bucket under boards/", "boards/HAA/%s.json" % D0 in bucket.store, list(bucket.store))
M._ROUTE_CACHE.clear()          # another instance: nothing in memory
window_calls.clear()
rows, age, hit = M._fetch_board("HAA", D0)
check("another instance reads the bucket and calls nothing", window_calls == [] and hit is True, window_calls)
check("its instants come back as datetimes, the same instant", rows[0]["_dep_utc"] == dep, rows[0]["_dep_utc"])
check("and board_is_cached says so without a call", M.board_is_cached("HAA", D0) is True and window_calls == [])
import json as _j   # noqa: E402
doc = _j.loads(bucket.store["boards/HAA/%s.json" % D0])
doc["fetched_at"] = (datetime.now(timezone.utc) - M.ROUTE_FUTURE_CACHE_TTL - timedelta(minutes=1)).isoformat()
bucket.store["boards/HAA/%s.json" % D0] = _j.dumps(doc).encode()
M._ROUTE_CACHE.clear()
check("a stored board past its twelve hours is not served", M.board_is_cached("HAA", D0) is False)
rows, age, hit = M._fetch_board("HAA", D0)
check("and is fetched again", len(window_calls) == 2 and hit is False, window_calls)
check("a rolling board has its own key", M._board_store_key("HAA", None) == "boards/HAA/rolling.json")
M._fetch_board_window = real_window
M.active_gateway = real_gateway
M._store_bucket = lambda: None
M._fetch_board = fake_fetch_board

print("\nPASSED: %d   FAILURES: %d" % (PASS, len(FAILURES)))
sys.exit(1 if FAILURES else 0)
