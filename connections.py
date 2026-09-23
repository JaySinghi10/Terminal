"""Connecting itineraries through one hub. docs/connection-search.md is the spec.

    search(origin, destination, date=None) -> dict          the whole answer
    search_events(origin, destination, date=None)           the same, as it happens

WHAT IT DOES, IN THE ORDER THE UNITS ARE SPENT:

  1  Both airports' ROUTE LISTS, 6 units each, cached 6 days in the bucket.
  2  Their INTERSECTION is the candidate hubs. Free.
  3  The DETOUR PRUNE drops any hub more than 1.4x out of the way. Free.
  4  The rest RANKED by daily flights on the thinner of the two legs. Free.
  5  The ORIGIN'S BOARD, which the direct search usually just loaded.
  6  EVERY SURVIVING HUB-DAY: the hub's board for each local day a workable
     second leg could leave on -- unless that day PROVABLY cannot beat the
     fastest itinerary already found, in which case it is skipped unfetched.

NO HUB CAP. Every hub is examined, and the only boards not fetched are the ones
a lower bound rules out -- so the fastest result is the fastest there is, among
the one-stop journeys the boards hold.

THE LOWER BOUND, and why it is a proof and not a guess. For a hub-day, the best
any itinerary through it can do is:

    (the first leg's own scheduled time, from the origin's board -- known)
  + (the wait until the second leg can leave: the minimum layover, and not
     before the start of that local day at the hub -- known)
  + (the second leg's great-circle distance / MAX_GROUND_SPEED_KMH -- a floor)

Every term is exact or an underestimate, so the sum is too. If it is not
strictly below the fastest found, no flight on that board can win.

IN PARALLEL, UP TO THE PROVIDER'S RATE. Hub-days are fetched through a sliding
window of PARALLEL_BOARDS at a time; mcp_server._rate_gate keeps the requests
inside the plan's limit. The bound is tested when a hub-day is SUBMITTED, against
the best found by then. Parallelism means a board can go out before a result
that would have ruled it out comes back, so a search may fetch a little more
than a one-at-a-time search would -- it never skips anything that could win.
Hub-days go out first-day-first across the hubs in rank order, so the next-day
boards, which the bound most often rules out, are tested last.

A RUNAWAY GUARD, NOT A BUDGET. UNIT_CEILING stops a search that would spend
more than 100 units. If it is ever reached, every hub-day left unfetched is
named in `unchecked`, `complete` is false, and the client must not call any
result the fastest: the proof above is only a proof when every hub-day was
either fetched or bounded out.

ONE STOP ONLY, and the itineraries are assembled from two independent boards,
so every one of them carries a transfer label (§8).
"""
import json
import logging
import math
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import mcp_server as M
import pollstate
from airport_geo import AIRPORT_GEO

logger = logging.getLogger("flight-tracker")

# ── THE ONE NUMBER HERE THAT IS A CONTRACT, NOT A TUNING ─────────────────────
#
# AeroDataBox confirmed the route list is Contents under their terms, however
# it is reshaped, and Contents may be cached for seven days at most. SIX leaves
# a day for a slow refresh or a skewed clock. It goes up only if the terms do.
# The bucket carries a lifecycle rule deleting routelists/ at six days as well,
# so the ceiling holds even if this code never runs again.
ROUTE_LIST_CACHE_TTL = timedelta(days=6)
ROUTE_LIST_PREFIX = "routelists/"

# What each provider call costs, as measured (§10).
ROUTE_LIST_UNITS = 6
BOARD_WINDOW_UNITS = 2

# §4. Tune on evidence and record it.
DETOUR_MAX = 1.4

# The runaway guard. See the module note. RAISED FROM 60: the first live search,
# Indore to Kochi fully cold, needed 56, so one more hub worth checking would
# have tripped it on an ordinary route.
UNIT_CEILING = 100

# HOW MANY HUB BOARDS ARE IN FLIGHT AT ONCE. A dated board is two requests, so
# three boards is up to six requests waiting on the gate, which starts four a
# second -- enough to keep the gate busy without queueing work the bound might
# yet rule out.
PARALLEL_BOARDS = 3

# §6. AN ESTIMATE, AND IT SAYS SO. No provider this app uses carries real
# minimum connection times; these do not know about terminal changes, the walk
# between two particular gates, or checked bags. The connection-delay warning
# uses the same two numbers, and if one changes both must.
MIN_LAYOVER_DOMESTIC = timedelta(minutes=60)
MIN_LAYOVER_INTERNATIONAL = timedelta(minutes=120)
MAX_LAYOVER = timedelta(hours=24)

# THE FLOOR ON A SECOND LEG'S DURATION. The fastest subsonic ground speed on
# record is about 1,327 km/h (a 747 in the North Atlantic jet stream, February
# 2020), and a SCHEDULED block time also carries taxi and climb. Dividing the
# great-circle distance by 1,350 therefore always underestimates a real
# scheduled leg, which is the only property the bound needs.
MAX_GROUND_SPEED_KMH = 1350

# §2. Rebuilt cheaply from cached boards, so kept short; a rolling search is
# kept only as long as the rolling board it came from, or its first legs would
# go on offering flights that have left.
RESULT_CACHE_TTL = timedelta(hours=4)
MAX_ITINERARIES = 25

_RESULTS = {}
_local_lists = {}      # the route-list store when there is no bucket (tests)


# ── DISTANCE ────────────────────────────────────────────────────────────────
def _km(a, b):
    """Great-circle kilometres between two (lat, lon, ...) tuples."""
    r, rad = 6371.0, math.pi / 180
    dlat = (b[0] - a[0]) * rad
    dlon = (b[1] - a[1]) * rad
    h = math.sin(dlat / 2) ** 2 + math.cos(a[0] * rad) * math.cos(b[0] * rad) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(h), math.sqrt(1 - h))


# ── THE BUDGET ──────────────────────────────────────────────────────────────
class _Budget:
    """Units committed this search. A board's cost is RESERVED when it is sent,
    so boards in flight at once cannot together pass the ceiling. The pace of
    the calls is mcp_server._rate_gate's job, not this."""

    def __init__(self, ceiling):
        self.ceiling = ceiling
        self.spent = 0

    def can(self, units):
        return self.spent + units <= self.ceiling

    def charge(self, units):
        self.spent += units


# ── ROUTE LISTS, IN THE BUCKET FOR SIX DAYS ─────────────────────────────────
def _bucket():
    return pollstate._bucket()


def _list_key(code):
    return f"{ROUTE_LIST_PREFIX}{code}.json"


def _read_list(code, now):
    """(routes, age) from the store, or (None, None). An entry at or past the
    contract ceiling is DELETED here, not merely ignored."""
    key = _list_key(code)
    bucket = _bucket()
    try:
        if bucket is None:
            doc = _local_lists.get(key)
        else:
            blob = bucket.get_blob(key)
            doc = None if blob is None else json.loads(blob.download_as_bytes().decode("utf-8"))
    except Exception:  # noqa: BLE001 -- an unreadable cache is a miss, never a failure
        return None, None
    if not isinstance(doc, dict):
        return None, None
    try:
        fetched = datetime.fromisoformat(doc["fetched_at"])
    except (KeyError, TypeError, ValueError):
        fetched = None
    if fetched is None or now - fetched >= ROUTE_LIST_CACHE_TTL:
        _delete_list(code)
        return None, None
    routes = doc.get("routes")
    return (routes, now - fetched) if isinstance(routes, list) else (None, None)


def _delete_list(code):
    key = _list_key(code)
    bucket = _bucket()
    try:
        if bucket is None:
            _local_lists.pop(key, None)
        else:
            blob = bucket.get_blob(key)
            if blob is not None:
                blob.delete()
    except Exception:  # noqa: BLE001
        logger.warning("connections: could not delete expired route list %s", code)


def _write_list(code, routes, now):
    doc = {"fetched_at": now.isoformat(), "routes": routes}
    bucket = _bucket()
    try:
        if bucket is None:
            _local_lists[_list_key(code)] = doc
        else:
            bucket.blob(_list_key(code)).upload_from_string(
                json.dumps(doc, separators=(",", ":")), content_type="application/json")
    except Exception:  # noqa: BLE001 -- a lost cache write costs units later, not correctness now
        logger.warning("connections: could not store route list %s", code)


def _parse_route_list(payload):
    """Only what the search reads: each destination's code, its average daily
    flights, and its country. Everything else in the response is dropped."""
    items = payload.get("routes") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return None
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        dest = it.get("destination") or {}
        code = str(dest.get("iata") or "").strip().upper()
        if not M._IATA_RE.match(code):
            continue
        try:
            daily = float(it.get("averageDailyFlights") or 0)
        except (TypeError, ValueError):
            daily = 0.0
        country = dest.get("countryCode")
        out.append({"iata": code, "daily": daily,
                    "country": str(country).upper() if country else None})
    return out


def _route_list(code, budget, now):
    """routes or None. Cached six days; the gate paces the call."""
    routes, _age = _read_list(code, now)
    if routes is not None:
        return routes
    if not budget.can(ROUTE_LIST_UNITS):
        return None
    budget.charge(ROUTE_LIST_UNITS)
    try:
        response = M._adb_get(f"/airports/iata/{code}/stats/routes/daily")
    except Exception:  # noqa: BLE001
        return None
    if response.status_code != 200 or not response.content:
        return None
    try:
        routes = _parse_route_list(response.json())
    except ValueError:
        routes = None
    if routes is None:
        return None
    _write_list(code, routes, now)
    return routes


# ── BOARDS, THROUGH THE SHARED CACHE ─────────────────────────────────────────
def _board_cost(code, day):
    """0 when the board is in memory or the bucket, else its provider cost."""
    if M.board_is_cached(code, day):
        return 0
    return BOARD_WINDOW_UNITS if day is None else BOARD_WINDOW_UNITS * len(M.ROUTE_DAY_WINDOWS)


# ── TIME ────────────────────────────────────────────────────────────────────
def _instant(iso):
    """An aware datetime from a board ISO, which carries its true offset."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _zone(name, fallback):
    try:
        return ZoneInfo(name) if name else fallback
    except Exception:  # noqa: BLE001
        return fallback


def _prefix(flight_number):
    """THE CARRIER IS THE FLIGHT NUMBER'S PREFIX, never the airline name: the
    provider files QP as "Starlight Airline" (§7)."""
    return str(flight_number or "")[:2].upper()


def _country(code, fallback=None):
    geo = AIRPORT_GEO.get(code)
    return geo[2] if geo is not None and geo[2] else fallback


# ── THE REPLY ───────────────────────────────────────────────────────────────
def _result(o, d, day, itineraries=None, complete=True, unchecked=None,
            hubs=None, units=0, error=None):
    """Every reply carries the same keys, as the direct search's does."""
    return {
        "origin": o,
        "destination": d,
        "date": day,
        "itineraries": itineraries or [],
        # FALSE WHEN THE RUNAWAY GUARD STOPPED THE SEARCH OR A BOARD FAILED. The
        # client must then call nothing the fastest: an unfetched hub-day might
        # have held a faster journey.
        "complete": complete,
        "unchecked": unchecked or [],
        "hubs": hubs or {},
        "units_spent": units,
        "error": error,
    }


def _emit(it, now):
    """One itinerary in the RouteItinerary shape Stage 1 built (§9)."""
    l1, l2 = it["leg1"], it["leg2"]
    return {
        "kind": "via",
        "legs": [M._emit_row(l1, now), M._emit_row(l2, now)],
        "hub": it["hub"],
        # The second leg leaves on a later local date than the first lands.
        "overnight": (l2.get("departure_scheduled_iso") or "")[:10]
                     > (l1.get("arrival_scheduled_iso") or "")[:10],
        "international": it["international"],
        # §8. EVERY ROW SPEAKS. Two independent boards cannot prove a
        # through-fare even on one carrier, so the same-carrier case is not
        # silent -- it says something different.
        "transfer": "same_carrier"
                    if _prefix(l1["flight_number"]) == _prefix(l2["flight_number"])
                    else "self",
    }


def _dedupe(found, origin, destination):
    """§7. THE SAME JOURNEY IS BOTH LEGS AT THE SAME INSTANTS BETWEEN THE SAME
    AIRPORTS. Keep the one whose two carriers match; failing that, the
    ALPHABETICALLY FIRST pair of flight numbers. That last rule is NOT a
    judgement of which is better -- it is the same aircraft either way. It is
    there so two searches of the same route return the same row, and the
    alphabet is the only tie-break that does not depend on the order the
    provider happened to send rows in.

    The identity includes the hub, so deduplicating one hub at a time is exact.
    """
    journeys = {}

    def rank(x):
        match = _prefix(x["leg1"]["flight_number"]) == _prefix(x["leg2"]["flight_number"])
        return (0 if match else 1, x["leg1"]["flight_number"], x["leg2"]["flight_number"])

    for it in found.values():
        l1, l2 = it["leg1"], it["leg2"]
        same = (l1["_dep_utc"], l1.get("origin_iata") or origin, it["hub"],
                l2["_dep_utc"], it["hub"], destination)
        prev = journeys.get(same)
        if prev is None or rank(it) < rank(prev):
            journeys[same] = it
    return sorted(journeys.values(),
                  key=lambda x: (x["journey"], x["leg1"]["_dep_utc"], x["leg1"]["flight_number"]))


# ── THE SEARCH ──────────────────────────────────────────────────────────────
def search(origin, destination, date=None):
    """The whole answer, as one dict: the last event of search_events."""
    final = None
    for event in search_events(origin, destination, date):
        if event["type"] == "done":
            final = {k: v for k, v in event.items() if k != "type"}
    return final


def search_events(origin, destination, date=None):
    """Yields {"type": "hub", ...} as each hub-day's board lands, carrying every
    itinerary through that hub found so far, then {"type": "done", ...} with the
    whole answer. A refusal is a single "done" carrying the error."""
    o = str(origin or "").strip().upper()
    d = str(destination or "").strip().upper()

    def done(**kw):
        return {"type": "done", **_result(o, d, kw.pop("day", None), **kw)}

    day, date_error = M._validate_route_date(date)
    if date_error is not None:
        yield done(error=date_error)
        return
    if not M._IATA_RE.match(o) or not M._IATA_RE.match(d):
        yield done(day=day, error="Origin and destination must both be 3-letter IATA codes.")
        return
    if o == d:
        yield done(day=day, error="Origin and destination must be different airports.")
        return
    if not M._adb_configured():
        yield done(day=day, error=M._adb_unconfigured("Connection search"))
        return
    geo_a, geo_b = AIRPORT_GEO.get(o), AIRPORT_GEO.get(d)
    if geo_a is None or geo_b is None:
        yield done(day=day, error=f"No position is known for {o if geo_a is None else d}.")
        return

    now = datetime.now(timezone.utc)
    key = (o, d, day)
    ttl = min(RESULT_CACHE_TTL, M.ROUTE_CACHE_TTL) if day is None else RESULT_CACHE_TTL
    hit = _RESULTS.get(key)
    if hit is not None and now - hit[0] < ttl:
        yield {"type": "done", **hit[1], "units_spent": 0}
        return

    budget = _Budget(UNIT_CEILING)

    # ── 1-2  THE ROUTE LISTS AND THEIR INTERSECTION ─────────────────────────
    list_a = _route_list(o, budget, now)
    list_b = _route_list(d, budget, now)
    if list_a is None or list_b is None:
        yield done(day=day, units=budget.spent,
                   error=f"Could not load the route list for {o if list_a is None else d}.")
        return
    # B's DESTINATIONS STAND IN FOR ITS ORIGINS (§3): scheduled service is
    # near-symmetric, not exactly. Cheap to be wrong about -- a hub the lists
    # admit wrongly finds no second leg on its board and yields nothing.
    by_b = {r["iata"]: r for r in list_b}
    candidates = [r for r in list_a if r["iata"] in by_b and r["iata"] not in (o, d)]

    # ── 3-4  THE DETOUR PRUNE AND THE RANK ──────────────────────────────────
    direct_km = _km(geo_a, geo_b)
    ranked, pruned, unplaced = [], [], []
    for r in candidates:
        geo_h = AIRPORT_GEO.get(r["iata"])
        if geo_h is None:
            unplaced.append(r["iata"])
            continue
        ratio = (_km(geo_a, geo_h) + _km(geo_h, geo_b)) / direct_km if direct_km > 0 else math.inf
        if ratio > DETOUR_MAX:
            pruned.append(r["iata"])
            continue
        ranked.append({
            "iata": r["iata"], "geo": geo_h,
            # THE THINNER LEG DECIDES. A hub with forty flights a day from the
            # origin and one onward is a one-flight hub.
            "daily": min(r["daily"], by_b[r["iata"]]["daily"]),
            "country": _country(r["iata"], r.get("country")),
        })
    ranked.sort(key=lambda h: (-h["daily"], h["iata"]))

    # ── 5  THE ORIGIN'S BOARD ───────────────────────────────────────────────
    cost = _board_cost(o, day)
    if not budget.can(cost):
        yield done(day=day, units=budget.spent, error="The search reached its unit ceiling.")
        return
    budget.charge(cost)
    rows_a, _age, _hit = M._fetch_board(o, day)
    if rows_a is None:
        yield done(day=day, units=budget.spent, error=f"Could not load the departure board for {o}.")
        return
    if day is None:
        horizon = now + timedelta(minutes=M.ROUTE_WINDOW_MINUTES)
        in_window = lambda r: now <= r["_dep_utc"] <= horizon  # noqa: E731
    else:
        in_window = lambda r: (r.get("departure_scheduled_iso") or "")[:10] == day  # noqa: E731
    first_legs = [
        r for r in rows_a
        if r.get("destination_iata") and in_window(r)
        and r["_dep_utc"] >= now                      # a flight that has left is no first leg
        and _instant(r.get("arrival_scheduled_iso")) is not None
        and not M._row_departed(r, now)
    ]

    # ── 6  THE HUB-DAYS, AND THE BOUND ON EACH ──────────────────────────────
    country_a, country_b = _country(o), _country(d)
    plans = {}                   # hub -> what pairing and the bound need
    work = []                    # (day index, rank, hub, local day), sent in that order
    no_first_leg = []
    for rank_i, hub in enumerate(ranked):
        h = hub["iata"]
        legs1 = [r for r in first_legs if r["destination_iata"] == h]
        if not legs1:
            no_first_leg.append(h)
            continue
        # UNKNOWN COUNTRY IS INTERNATIONAL, the stricter reading (§6).
        international = None in (country_a, hub["country"], country_b) \
            or len({country_a, hub["country"], country_b}) > 1
        minimum = MIN_LAYOVER_INTERNATIONAL if international else MIN_LAYOVER_DOMESTIC
        windows = []
        for r in legs1:
            arr = _instant(r["arrival_scheduled_iso"])
            tz = _zone(r.get("arrival_timezone"), arr.tzinfo)
            windows.append((r, tz, arr + minimum, arr + MAX_LAYOVER))
        days = sorted({
            (start.astimezone(tz) + timedelta(days=k)).date().isoformat()
            for (_r, tz, start, end) in windows
            for k in range((end.astimezone(tz).date() - start.astimezone(tz).date()).days + 1)
        })
        plans[h] = {"windows": windows, "international": international, "rows": [],
                    "floor": timedelta(hours=_km(hub["geo"], geo_b) / MAX_GROUND_SPEED_KMH),
                    "found": {}}
        for day_i, hub_day in enumerate(days):
            work.append((day_i, rank_i, h, hub_day))
    work.sort()

    def bound(h, hub_day):
        """The least journey time any itinerary on this hub-day could have, or
        None when no first leg's window reaches the day."""
        p = plans[h]
        best_b = None
        for (r, tz, start, end) in p["windows"]:
            day_start = datetime.fromisoformat(hub_day).replace(tzinfo=tz)
            if end < day_start or start >= day_start + timedelta(days=1):
                continue
            b = (max(start, day_start) - r["_dep_utc"]) + p["floor"]
            best_b = b if best_b is None or b < best_b else best_b
        return best_b

    def pair(h):
        """Every first leg at this hub with its best second leg among the rows
        fetched so far. Returns the fastest journey found."""
        p = plans[h]
        fastest = None
        for (r, _tz, start, end) in p["windows"]:
            pick = None
            for s in p["rows"]:
                if s.get("destination_iata") != d or (s.get("origin_iata") or h) != h:
                    continue
                dep2 = s["_dep_utc"]
                arr2 = _instant(s.get("arrival_scheduled_iso"))
                if arr2 is None or dep2 < start or dep2 > end or arr2 <= dep2:
                    continue
                # THE EARLIEST ARRIVAL, not the earliest departure: a later flight
                # can land first. Ties go by the codeshare rule -- the carrier
                # matching the first leg's, then the alphabet -- so one aircraft
                # sold under two numbers resolves here as it does in _dedupe.
                rk = (arr2, dep2,
                      0 if _prefix(s["flight_number"]) == _prefix(r["flight_number"]) else 1,
                      s["flight_number"])
                if pick is None or rk < pick[2]:
                    pick = (s, arr2, rk)
            if pick is None:
                continue
            s, arr2, _rk = pick
            journey = arr2 - r["_dep_utc"]
            p["found"][(r["_dep_utc"], r["flight_number"], s["_dep_utc"], s["flight_number"])] = {
                "leg1": r, "leg2": s, "hub": h, "journey": journey,
                "international": p["international"]}
            fastest = journey if fastest is None or journey < fastest else fastest
        return fastest

    best = None
    checked, bounded, unchecked, failed = [], [], [], []
    queue = list(work)
    in_flight = {}
    with ThreadPoolExecutor(max_workers=PARALLEL_BOARDS) as pool:
        while queue or in_flight:
            # FILL THE WINDOW, testing each hub-day's bound as it is SENT.
            while queue and len(in_flight) < PARALLEL_BOARDS:
                _di, _ri, h, hub_day = queue.pop(0)
                b = bound(h, hub_day)
                if b is None:
                    continue
                if best is not None and b >= best:
                    bounded.append(f"{h} {hub_day}")
                    continue
                c = _board_cost(h, hub_day)
                if not budget.can(c):
                    unchecked.append(f"{h} {hub_day}")
                    continue
                budget.charge(c)
                in_flight[pool.submit(M._fetch_board, h, hub_day)] = (h, hub_day)
            if not in_flight:
                break
            finished, _pending = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in finished:
                h, hub_day = in_flight.pop(fut)
                try:
                    rows, _age, _hit = fut.result()
                except Exception:  # noqa: BLE001
                    rows = None
                if rows is None:
                    failed.append(f"{h} {hub_day}")
                    continue
                checked.append(f"{h} {hub_day}")
                plans[h]["rows"].extend(rows)
                fastest = pair(h)
                if fastest is not None and (best is None or fastest < best):
                    best = fastest
                # AS IT LANDS. Everything through this hub so far; a later event
                # for the same hub replaces it.
                yield {"type": "hub", "hub": h, "day": hub_day,
                       "itineraries": [_emit(it, now) for it in _dedupe(plans[h]["found"], o, d)]}

    everything = {}
    for p in plans.values():
        everything.update(p["found"])
    ordered = _dedupe(everything, o, d)
    complete = not unchecked and not failed
    result = _result(
        o, d, day,
        itineraries=[_emit(it, now) for it in ordered[:MAX_ITINERARIES]],
        complete=complete,
        unchecked=unchecked + failed,
        hubs={
            "candidates": len(candidates),
            "pruned_by_detour": pruned,
            "no_position": unplaced,
            "ranked": [h["iata"] for h in ranked],
            "no_first_leg": no_first_leg,
            "checked": checked,
            "bounded_out": bounded,
            "failed": failed,
        },
        units=budget.spent,
    )
    # A SEARCH THE GUARD STOPPED IS NOT KEPT, so the next attempt gets to finish.
    if complete:
        _RESULTS[key] = (now, result)
    yield {"type": "done", **result}
