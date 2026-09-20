"""Which changes are worth waking someone for, and what to say.

WHAT THIS IS. The poller records every change it sees in a ledger (see the
`pending` list in pollstate). Most of those changes are not worth a
notification: an estimate drifting by two minutes, a gate flapping seventeen
hours before departure, an arrival gate nobody acts on. This module holds the
rules that turn the CURRENT record into the few messages a person would want,
and the text of each.

THE ONE PRINCIPLE EVERYTHING FOLLOWS FROM: a message is derived from the
current record against the last state we TOLD the person, never from the
change entries one by one. The entries are folded into the record before this
runs, and one decision runs. So a gate that goes 84, 87A, 84 between two polls
is invisible, because the current value equals the last one notified; and a
revert AFTER a message was sent is a real change and gets its own message.

WHAT IS SENT IS FACTS, NOT SENTENCES. A message in the outbox carries the
kind, the flight, both cities, the scheduled time and the values that changed.
The sentence is written at delivery, by render(), when the sender has the
recipient's own watch list in hand -- because the SUBJECT of the sentence
depends on who is reading it. "Your flight to Bangalore" is right for the
person on it; "The flight from Mumbai" is right for the person meeting it; and
someone watching two flights to the same city that day needs the time in the
subject. See subject().

NOTHING HERE SENDS. Push needs a dev build that does not exist yet. The outbox
fills, bounded, and the sender drains it when it exists. See the note at the
top of pollstate.py.

NEVER SEND THE PERSON TO THE AIRLINE. A cancellation names the next departure
on the route, found with the same route board the app uses; if nothing leaves
for days the search continues across polls and names the first flight that
does exist, however far out. A diversion says plainly that the aircraft went
somewhere else and that we do not yet know where, because the schedule
provider carries no diversion airport.

NEVER CLAIM WHAT THE DATA DOES NOT SUPPORT. An estimate is "around"; a fact
from a landing feed is a plain time; a gate we were not given is not mentioned;
a "departed" is only said once the actual time is in the past AND has held for
two polls, because the provider has been seen to revise an "actual" by
fifty-three minutes (6E6188, 7 Sep 2026, in the ledger).
"""
import hashlib
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

# ── KINDS ───────────────────────────────────────────────────────────────────
CANCELLED = "cancelled"
CANCEL_WITHDRAWN = "cancel_withdrawn"
NEXT_FLIGHT = "next_flight"          # the follow-up when the search finds one later
GATE = "gate"
GATE_CAP = "gate_cap"
TERMINAL = "terminal"
DELAY = "delay"
ON_TIME = "on_time"
DEPARTED = "departed"
ARRIVAL_MOVED = "arrival_moved"
ARRIVAL_TERMINAL = "arrival_terminal"
LANDED = "landed"
BELT = "belt"
DIVERTED = "diverted"
# A DELAY THAT THREATENS THE NEXT LEG. See CONNECT_MIN_DOMESTIC below for the
# arithmetic and for what it does not know.
CONNECTION = "connection"

# ── THE WINDOWS ─────────────────────────────────────────────────────────────
# A gate change three days out is not the same as one while she is walking to
# the gate. Outside these windows the change is swallowed; the app shows the
# current value whenever it is opened.
GATE_WINDOW = timedelta(hours=4)
TERMINAL_WINDOW = timedelta(hours=24)
DELAY_WINDOW = timedelta(hours=12)
BELT_WINDOW = timedelta(minutes=90)

# ── THE THRESHOLDS ──────────────────────────────────────────────────────────
DELAY_MIN = timedelta(minutes=15)       # the first delay notice
DELAY_STEP = timedelta(minutes=15)      # a further notice needs this much movement
DELAY_FLOOR = timedelta(minutes=30)     # ...and this long since the last one
ON_TIME_TOLERANCE = timedelta(minutes=5)
ARRIVAL_STEP = timedelta(minutes=15)

# A VALUE MUST HOLD FOR TWO CONSECUTIVE POLLS before it is worth a message:
# a gate that flips and flips back inside one poll interval was never the gate.
# Cancellation, landing and diversion are exempt -- a landing is already
# confirmed by the feed, and a cancellation that waits thirty minutes at the
# day tier is a cancellation the person hears about late.
SETTLE_POLLS = 2

GATE_CAP_COUNT = 3                      # gate messages per flight, then one cap notice
BELT_CAP_COUNT = 2
# One message per flight per twenty minutes, so a busy ten minutes does not
# become five buzzes. Cancelled, landed and diverted are exempt.
FLIGHT_FLOOR = timedelta(minutes=20)
# Belt is exempt too: it follows a landing by minutes, is capped at two, and
# is the one thing the person at arrivals is waiting to hear.
FLOOR_EXEMPT = {CANCELLED, CANCEL_WITHDRAWN, LANDED, DIVERTED, NEXT_FLIGHT, BELT, CONNECTION}

# ── WHETHER THE CONNECTION CAN STILL BE MADE ────────────────────────────────
#
# THE REMAINING LAYOVER IS THE LATER LEG'S DEPARTURE MINUS THIS ONE'S REVISED
# ARRIVAL, where revised is actual, then estimated, then scheduled -- the same
# precedence poller._movement_time already uses to tier a flight, and the same
# one the app's arrivalTs uses to draw it.
#
# THE LATER LEG IS TAKEN AT ITS TIMETABLE, DELIBERATELY. A delay on the
# connecting flight would lengthen the layover and could silence this warning,
# and it is the one input here that can be recovered at any moment. Telling
# somebody their connection is fine because the flight they need to catch is
# also running late is the one way this could be actively harmful.
#
# THE MINIMUM IS AN ESTIMATE AND THIS COMMENT IS WHERE IT SAYS SO. No provider
# in this app carries real minimum connection times: every airport publishes its
# own, they differ per terminal pair, and none of them is in any feed we read.
# Sixty minutes domestic and a hundred and twenty international are the common
# industry shape and nothing more. THEY DO NOT ACCOUNT FOR A TERMINAL CHANGE,
# which is the thing most likely to make a real connection tighter than this
# arithmetic says, nor for the walk between two gates, nor for bags to reclaim.
#
# SHARED WITH THE APP, WHICH HAS ITS OWN COPY. lib/saved.tsx's connectionRisk
# computes the same three bands from the same four numbers so a push and a
# screen cannot disagree. There is no shared runtime between Python and
# TypeScript, so the two are restated rather than imported -- the arrangement
# MAX_LAYOVER_MS already has with MAX_CONNECTION_MS. Change one, change both.
CONNECT_MIN_DOMESTIC = timedelta(minutes=60)
CONNECT_MIN_INTERNATIONAL = timedelta(minutes=120)
CONNECT_CUSHION = timedelta(minutes=30)
# Worse is later in this tuple, which is the whole of "the band worsened".
CONNECT_BANDS = ("comfortable", "at_risk", "will_miss")
# A connection at all, on the same window the app's MAX_CONNECTION_MS uses.
CONNECT_MAX = timedelta(hours=24)

# A cancellation of a flight more than a day away that lands in the night at
# the departure airport is DEFERRED to seven in the morning there, not dropped.
QUIET_START_HOUR = 22
QUIET_END_HOUR = 7
QUIET_ONLY_BEYOND = timedelta(hours=24)

# ── THE NEXT-FLIGHT SEARCH ──────────────────────────────────────────────────
# A dated board costs two provider calls (the provider caps a range at twelve
# hours, so a day is two windows). The first pass looks three days ahead in
# the same poll, which is the common case answered at once; after that the
# search continues two days per poll until it finds a flight or reaches the
# ceiling below.
NEXT_FIRST_PASS_DAYS = 3
NEXT_DAYS_PER_POLL = 2

# ── A WEEK, WHICH USED TO BE SIXTY DAYS ─────────────────────────────────────
#
# IT WAS mcp_server.ROUTE_MAX_FUTURE_DAYS -- how far the SCHEDULE reaches --
# and that was the wrong quantity. How far the timetable is published is a fact
# about the provider; how far a stranded passenger will read is a fact about
# the passenger, and the second is the one this search is for. Nobody whose
# flight was cancelled this morning is served by a departure seven weeks out.
#
# AND SIXTY DAYS WAS THE APP'S LARGEST SINGLE SPEND. A route with no service
# walked every one of them: 60 days x 4 units = 240 units for one cancellation,
# spread over about thirty polls. A hundred such cancellations in a month is
# 24,000 units against a 40,000 allowance. Seven days costs 28, and the walk
# finishes in three polls instead of thirty.
#
# THE COPY IS COUPLED TO THIS NUMBER AND DOES NOT READ IT. Both exhausted
# sentences say "in the next week" in words -- see render -- because "the next 7
# days" reads like a machine and a week does not. CHANGE ONE, CHANGE BOTH.
NEXT_MAX_DAYS = 7
NEXT_CALLS_PER_DAY = 2

# ── HOW SOON A REPLACEMENT CAN BE, AND STILL BE ONE ─────────────────────────
#
# NINETY MINUTES, WHICH IS poller.NEAR_BEFORE_DEPARTURE. That constant is this
# app's existing answer to "how long before a departure does it start to
# matter", so a flight closer than that is one the reader cannot realistically
# reach, and offering it would be the app being confidently useless.
#
# IT REPLACES A FLOOR THAT WAS ANCHORED TO THE DEAD FLIGHT. The filter used to
# be max(scheduled departure, now), which excluded every alternative leaving
# BEFORE the cancelled one -- so a 21:30 cancelled at 16:30 hid the 20:00 on
# the same route, the single best option for somebody already at the airport.
# The further ahead a cancellation landed, the more it hid.
#
# THE DAY LOOP IS NOT MOVED BY THIS, and that is the half worth stating. It
# still begins on the cancelled flight's own date; only the row filter moved.
# Anchoring the loop to `now` instead would make a cancellation three days out
# walk today, tomorrow and the next day -- three boards, twelve units -- before
# reaching the date anybody is travelling on.
NEXT_MIN_LEAD = timedelta(minutes=90)

# ── AND HOW MANY OF THEM ARE KEPT ───────────────────────────────────────────
#
# THE BOARD WAS FETCHED AND ALL BUT ONE ROW THROWN AWAY. The search kept the
# earliest qualifying departure and discarded the rest of a board already paid
# for; the drawer needs a list, and this is that list at no extra cost.
#
# EIGHT, which fills a drawer section and is well inside the 25 a board returns.
#
# FROM THE FIRST PRODUCTIVE DAY ONLY, and never accumulated across days. A day
# that yields two rows returns two -- reaching eight by walking further would
# spend four units a day to lengthen a list whose first entry is already the
# answer, on exactly the thin routes that can least afford it.
NEXT_KEEP_ROWS = 8

OUTBOX_MAX = 40

STATUS_CANCELLED = "cancelled"
STATUS_DIVERTED = "diverted"
LANDING_LANDED = "landed"


# ── TIME HELPERS ────────────────────────────────────────────────────────────
def _parse(iso):
    """An aware datetime from the DTO's ISO strings, or None."""
    if not iso or not isinstance(iso, str):
        return None
    s = iso.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _clock(dt):
    """'9:30 PM' -- the DTO's own style, so computed times read like given ones."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _tz_label(dto_time_string):
    """'IST' from '9:30 PM IST'. The DTO already carries the airport's label;
    reusing it is how a computed time never invents a zone name."""
    parts = str(dto_time_string or "").split()
    return parts[-1] if len(parts) >= 3 else ""


def _minutes(td):
    return int(round(td.total_seconds() / 60))


def _duration(td):
    m = abs(_minutes(td))
    if m < 60:
        return "%d min" % m
    h, r = divmod(m, 60)
    return "%d h" % h if r == 0 else "%d h %02d min" % (h, r)


def _day_label(dt, now):
    """'today', 'tomorrow', 'Thursday', or '25 Sep' when it is a week or more."""
    d = (dt.date() - now.astimezone(dt.tzinfo).date()).days
    if d <= 0:
        return "today"
    if d == 1:
        return "tomorrow"
    if d < 7:
        return dt.strftime("%A")
    return dt.strftime("%d %b").lstrip("0")


# ── THE RECORD, READ ────────────────────────────────────────────────────────
def _facts(dto):
    dep, arr = dto.get("departure") or {}, dto.get("arrival") or {}
    return {
        "flight_number": dto.get("flight_number"),
        "flight_date": dto.get("flight_date"),
        "airline": dto.get("airline"),
        "origin": {"iata": dep.get("iata"), "city": dep.get("city")},
        "destination": {"iata": arr.get("iata"), "city": arr.get("city")},
        "scheduled_departure": dep.get("scheduled"),
        "scheduled_departure_iso": dep.get("scheduled_iso"),
        "scheduled_arrival": arr.get("scheduled"),
        "scheduled_arrival_iso": arr.get("scheduled_iso"),
    }


def _key(facts, kind, value=""):
    raw = "%s|%s|%s|%s" % (facts.get("flight_number"), facts.get("flight_date"), kind, value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def blank_notify_state():
    return {
        "version": 1,
        "seeded": False,
        "notified": {},        # field -> value last told
        "settle": {},          # field -> {"value", "polls"}
        "counts": {},          # kind -> messages sent
        "last_msg_at": None,
        "last_delay_at": None,
        "last_arrival_at": None,
        "outbox": [],
        "keys": [],
        "next_search": None,
    }


def _settled(ns, field, value):
    """True once `value` has been seen SETTLE_POLLS polls in a row."""
    cur = ns["settle"].get(field)
    if cur and cur.get("value") == value:
        cur["polls"] = int(cur.get("polls", 0)) + 1
    else:
        ns["settle"][field] = cur = {"value": value, "polls": 1}
    return cur["polls"] >= SETTLE_POLLS


# ── THE DECISION ────────────────────────────────────────────────────────────
def decide(ns, dto, landing, now, lookup_next=None, connection=None):
    """(new_state, messages). dto is the CURRENT record; landing the current
    landing answer or None; lookup_next(origin, dest, day) -> rows, or None
    when the caller has no budget for it this poll.

    connection is the DTO of the leg this one connects INTO, or None when there
    is no next leg or the caller could not resolve one. It is read-only and
    costs nothing: the caller has already loaded it from state. See
    connection_band.

    Pure over its inputs apart from lookup_next, which is the one call that
    leaves the process, and it is only made on a cancellation."""
    ns = dict(ns or blank_notify_state())
    ns["settle"] = dict(ns.get("settle") or {})
    ns["notified"] = dict(ns.get("notified") or {})
    ns["counts"] = dict(ns.get("counts") or {})
    ns["keys"] = list(ns.get("keys") or [])
    ns["outbox"] = list(ns.get("outbox") or [])
    out = []
    if not isinstance(dto, dict):
        return ns, out

    facts = _facts(dto)
    dep, arr = dto.get("departure") or {}, dto.get("arrival") or {}
    sched_dep = _parse(dep.get("scheduled_iso"))
    sched_arr = _parse(arr.get("scheduled_iso"))
    est_dep = _parse(dep.get("estimated_iso"))
    act_dep = _parse(dep.get("actual_iso"))
    est_arr = _parse(arr.get("estimated_iso"))
    status = dto.get("status")
    landed = isinstance(landing, dict) and landing.get("outcome") == LANDING_LANDED
    before_dep = sched_dep is not None and now < sched_dep
    until_dep = (sched_dep - now) if before_dep else timedelta(0)
    departed_told = "departed" in ns["notified"]

    # ── FIRST SIGHT SEEDS AND SAYS NOTHING. Everything about a flight is new
    # the first time; reporting it would be a notification per field.
    if not ns.get("seeded"):
        ns["seeded"] = True
        ns["notified"].update({
            "gate": dep.get("gate"), "terminal": dep.get("terminal"),
            "arrival_terminal": arr.get("terminal"),
            "status": status,
            "delay_min": 0,
        })
        if act_dep is not None and now > act_dep:
            ns["notified"]["departed"] = dep.get("actual_iso")
            due = est_arr or sched_arr
            ns["last_arrival_at"] = _iso(due) if due else None
        if landed:
            ns["notified"]["landed"] = landing.get("landed_utc")
            ns["notified"]["belt"] = arr.get("baggage")
        return ns, out

    def emit(kind, values, deliver_after=None, key_value=""):
        k = _key(facts, kind, key_value)
        if k in ns["keys"]:
            return False
        last = _parse(ns.get("last_msg_at"))
        if kind not in FLOOR_EXEMPT and last is not None and now - last < FLIGHT_FLOOR:
            return False
        msg = dict(facts)
        msg.update({"key": k, "kind": kind, "at": _iso(now),
                    "deliver_after": _iso(deliver_after) if deliver_after else None,
                    "values": values})
        out.append(msg)
        ns["keys"] = (ns["keys"] + [k])[-200:]
        ns["outbox"] = (ns["outbox"] + [msg])[-OUTBOX_MAX:]
        ns["counts"][kind] = int(ns["counts"].get(kind, 0)) + 1
        ns["last_msg_at"] = _iso(now)
        return True

    # ── CANCELLED ── any time before departure, deferred through the night when far out
    if status == STATUS_CANCELLED and ns["notified"].get("status") != STATUS_CANCELLED:
        ns["notified"]["status"] = STATUS_CANCELLED
        deliver_after = _quiet_deferral(now, sched_dep, dep.get("timezone"))
        found, search = _search_next(facts, dto, now, None, lookup_next, NEXT_FIRST_PASS_DAYS)
        ns["next_search"] = search
        values = {"next": found, "searching": found is None and not search.get("done")}
        if found is None and search.get("done"):
            values["none_within_days"] = NEXT_MAX_DAYS
        emit(CANCELLED, values, deliver_after=deliver_after)
        return ns, out

    # ── THE SEARCH CONTINUES across polls until it finds a flight or hits the ceiling
    search = ns.get("next_search")
    if search and not search.get("done") and lookup_next is not None:
        found, search = _search_next(facts, dto, now, search, lookup_next, NEXT_DAYS_PER_POLL)
        ns["next_search"] = search
        if found is not None:
            emit(NEXT_FLIGHT, {"next": found}, key_value=found.get("flight_number", ""))
        elif search.get("done"):
            emit(NEXT_FLIGHT, {"next": None, "none_within_days": NEXT_MAX_DAYS})

    if ns["notified"].get("status") == STATUS_CANCELLED:
        if status != STATUS_CANCELLED and status is not None:
            ns["notified"]["status"] = status
            emit(CANCEL_WITHDRAWN, {"scheduled": dep.get("scheduled")})
        return ns, out

    # ── DIVERTED
    if status == STATUS_DIVERTED and ns["notified"].get("status") != STATUS_DIVERTED:
        ns["notified"]["status"] = STATUS_DIVERTED
        emit(DIVERTED, {})

    # ── THE CONNECTION THIS LEG FEEDS ──────────────────────────────────────
    #
    # BEFORE EVERY RETURN BELOW, because a delay eats a layover in all three
    # phases: before departure, in the air running late, and at the moment of
    # landing -- which is when the worst version of this news arrives and is
    # exactly the poll that would otherwise return early on LANDED.
    #
    # ONLY WHEN THE BAND WORSENS, and once per band. Keyed on the band itself,
    # so comfortable -> at_risk sends one message and at_risk -> will_miss
    # sends a second, while twenty polls inside one band send nothing. An
    # improving connection says nothing at all: this warns and never reassures,
    # the same rule the app's layover row follows.
    #
    # NOT FOR A CANCELLED OR DIVERTED LEG. Cancelled has already returned above;
    # diverted is guarded here. Both have their own message, and a connection
    # off a flight that is not going there is not the news.
    if connection is not None and status not in (STATUS_CANCELLED, STATUS_DIVERTED):
        judged = connection_band(dto, connection, now)
        if judged is not None:
            band, remaining, minimum = judged
            told = ns["notified"].get("connection_band") or "comfortable"
            if CONNECT_BANDS.index(band) > CONNECT_BANDS.index(told):
                ns["notified"]["connection_band"] = band
                nxt_dep = (connection.get("departure") or {})
                emit(CONNECTION, {
                    "band": band,
                    "remaining_min": _minutes(remaining),
                    "minimum_min": _minutes(minimum),
                    "hub": nxt_dep.get("city") or nxt_dep.get("airport") or nxt_dep.get("iata"),
                    "next": {
                        "flight_number": connection.get("flight_number"),
                        "date": connection.get("flight_date"),
                    },
                }, key_value=band)

    # ── LANDED ── once, from the landing feed only
    if landed and "landed" not in ns["notified"]:
        ns["notified"]["landed"] = landing.get("landed_utc")
        when = _parse(landing.get("landed_utc"))
        local = _to_zone(when, arr.get("timezone"))
        belt = arr.get("baggage")
        if belt:
            ns["notified"]["belt"] = belt
            ns["counts"][BELT] = int(ns["counts"].get(BELT, 0)) + 1
        emit(LANDED, {"time": _clock(local) if local else None,
                      "tz": _tz_label(arr.get("scheduled")),
                      "belt": belt,
                      "elsewhere": bool(landing.get("diverted_to"))})
        return ns, out

    # ── BELT ── only after landing, inside the window
    if "landed" in ns["notified"]:
        when = _parse(ns["notified"].get("landed"))
        belt = arr.get("baggage")
        if (belt and belt != ns["notified"].get("belt") and when is not None
                and now - when <= BELT_WINDOW
                and int(ns["counts"].get(BELT, 0)) < BELT_CAP_COUNT
                and _settled(ns, "belt", belt)):
            ns["notified"]["belt"] = belt
            emit(BELT, {"belt": belt}, key_value=belt)
        return ns, out

    # ── DEPARTED ── the actual is in the past and has held for two polls
    if not departed_told and act_dep is not None and now > act_dep:
        if _settled(ns, "departed", dep.get("actual_iso")):
            ns["notified"]["departed"] = dep.get("actual_iso")
            due = est_arr or sched_arr
            ns["last_arrival_at"] = _iso(due) if due else None
            emit(DEPARTED, {"due": _clock(due) if due else None,
                            "tz": _tz_label(arr.get("scheduled"))})
            return ns, out

    # ── AFTER DEPARTURE: the person meeting the flight
    if departed_told:
        if est_arr is not None:
            last = _parse(ns.get("last_arrival_at"))
            if last is None or abs(est_arr - last) >= ARRIVAL_STEP:
                last_msg = _parse(ns.get("last_msg_at"))
                if last_msg is None or now - last_msg >= DELAY_FLOOR:
                    delta = est_arr - last if last is not None else timedelta(0)
                    if emit(ARRIVAL_MOVED, {"due": _clock(est_arr), "tz": _tz_label(arr.get("scheduled")),
                                            "later_by": _minutes(delta)}):
                        ns["last_arrival_at"] = _iso(est_arr)
        at = arr.get("terminal")
        if at and ns["notified"].get("arrival_terminal") and at != ns["notified"]["arrival_terminal"]:
            if _settled(ns, "arrival_terminal", at):
                emit(ARRIVAL_TERMINAL, {"terminal": at, "was": ns["notified"]["arrival_terminal"]}, key_value=at)
                ns["notified"]["arrival_terminal"] = at
        return ns, out

    # ── BEFORE DEPARTURE ──
    # Terminal: inside 24 hours, on a change from the known value
    term = dep.get("terminal")
    if (before_dep and until_dep <= TERMINAL_WINDOW and term
            and ns["notified"].get("terminal") and term != ns["notified"]["terminal"]
            and _settled(ns, "terminal", term)):
        if emit(TERMINAL, {"terminal": term, "was": ns["notified"]["terminal"]}, key_value=term):
            ns["notified"]["terminal"] = term

    # Gate: inside four hours, settled, against the last gate TOLD, capped.
    #
    # THE BASELINE IS TAKEN WHEN THE WINDOW OPENS. Whatever the gate is at
    # four hours out is the known gate from then on -- the app shows it, and
    # nothing about it is news. Only what changes INSIDE the window is a
    # message; seven changes at seventeen hours out are not, and neither is the
    # difference between the gate seeded a day ago and the one at T-4h.
    gate = dep.get("gate")
    in_gate_window = before_dep and until_dep <= GATE_WINDOW
    if in_gate_window and not ns.get("gate_window_open"):
        ns["gate_window_open"] = True
        ns["notified"]["gate"] = gate
        ns["settle"].pop("gate", None)
    elif in_gate_window and gate and gate != ns["notified"].get("gate"):
        if _settled(ns, "gate", gate):
            n = int(ns["counts"].get(GATE, 0))
            if n < GATE_CAP_COUNT:
                if emit(GATE, {"gate": gate, "was": ns["notified"].get("gate"), "terminal": term}, key_value=gate):
                    ns["notified"]["gate"] = gate
            elif int(ns["counts"].get(GATE_CAP, 0)) == 0:
                emit(GATE_CAP, {})
                ns["notified"]["gate"] = gate

    # Delay: inside twelve hours, in bands of fifteen minutes, thirty minutes apart
    if before_dep and until_dep <= DELAY_WINDOW and sched_dep is not None:
        delay = (est_dep - sched_dep) if est_dep is not None else timedelta(0)
        told = timedelta(minutes=int(ns["notified"].get("delay_min") or 0))
        last = _parse(ns.get("last_delay_at"))
        floor_ok = last is None or now - last >= DELAY_FLOOR
        tz = _tz_label(dep.get("scheduled"))
        if delay >= DELAY_MIN and abs(delay - told) >= DELAY_STEP and floor_ok:
            if _settled(ns, "delay", _minutes(delay)):
                kind_hint = "first" if told < DELAY_MIN else ("more" if delay > told else "less")
                if emit(DELAY, {"delay_min": _minutes(delay), "expected": _clock(est_dep), "tz": tz,
                                "change": kind_hint}, key_value=str(_minutes(delay))):
                    ns["notified"]["delay_min"] = _minutes(delay)
                    ns["last_delay_at"] = _iso(now)
        elif delay <= ON_TIME_TOLERANCE and told >= DELAY_MIN and floor_ok:
            if _settled(ns, "delay", _minutes(delay)):
                if emit(ON_TIME, {"scheduled": dep.get("scheduled")}):
                    ns["notified"]["delay_min"] = 0
                    ns["last_delay_at"] = _iso(now)

    return ns, out


def _to_zone(dt, tz_name):
    if dt is None:
        return None
    if tz_name and ZoneInfo is not None:
        try:
            return dt.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    return dt


def _quiet_deferral(now, sched_dep, tz_name):
    """07:00 local at the departure airport, when a cancellation of a flight
    more than a day away lands in the night there. Otherwise None."""
    if sched_dep is None or sched_dep - now <= QUIET_ONLY_BEYOND:
        return None
    local = _to_zone(now, tz_name)
    if local.hour >= QUIET_START_HOUR:
        target = (local + timedelta(days=1)).replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    elif local.hour < QUIET_END_HOUR:
        target = local.replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    else:
        return None
    return target.astimezone(timezone.utc)


def _country(dto, movement):
    """The country of one end of a leg, or None when the DTO predates the field.

    None IS NOT 'DOMESTIC'. A record stored before _build_movement carried the
    country has none, and every one of them would otherwise look like a
    domestic connection and be given the shorter minimum. connection_band reads
    a None as a border crossing for exactly that reason; it corrects itself the
    first time the flight is re-polled.
    """
    return ((dto or {}).get(movement) or {}).get("country") or None


def connection_band(dto, nxt, now=None):
    """(band, remaining, minimum) for this leg into the next, or None.

    None when the two do not connect, when either instant is unreadable, or
    when the gap is wider than a day -- which is a stay between two journeys
    rather than a layover. See CONNECT_MIN_DOMESTIC for what the minimum is
    and for what it does not account for.
    """
    dep = (dto or {}).get("departure") or {}
    arr = (dto or {}).get("arrival") or {}
    nxt_dep = (nxt or {}).get("departure") or {}
    nxt_arr = (nxt or {}).get("arrival") or {}

    hub = (arr.get("iata") or "").strip().upper()
    if not hub or hub != (nxt_dep.get("iata") or "").strip().upper():
        return None

    # REVISED, in the one precedence this whole system uses for a movement.
    landed_at = _parse(arr.get("actual_iso")) or _parse(arr.get("estimated_iso")) \
        or _parse(arr.get("scheduled_iso"))
    # AND THE TIMETABLE ON THE OTHER SIDE. See the note above CONNECT_MIN_DOMESTIC.
    leaves_at = _parse(nxt_dep.get("scheduled_iso"))
    if landed_at is None or leaves_at is None:
        return None

    remaining = leaves_at - landed_at
    if remaining >= CONNECT_MAX:
        return None

    minimum = connection_minimum(dto, nxt)
    return _band(remaining, minimum), remaining, minimum


# ── THE MINIMUM FOR THIS JOURNEY'S HUB, LIFTED OUT OF connection_band ───────
#
# TWO CALLERS NOW AND THE RULE MUST NOT BE WRITTEN TWICE. The warning asks
# "will the leg you are on make the leg you booked"; the drawer asks "would
# this REPLACEMENT make it". Same hub, same three countries, same threshold --
# and two copies of a border test is exactly how the warning and the list come
# to disagree about whether one connection is domestic.
#
# THE REPLACEMENT FLIES THE SAME CITY PAIR, which is why this works unchanged
# for it. A board row carries no country at all -- only IATA codes -- but a
# replacement for a cancelled BOM->DEL leg is itself BOM->DEL, so the countries
# are the cancelled leg's own and are read from its DTO.
#
# EITHER LEG CROSSING A BORDER RAISES THE MINIMUM, which is three countries:
# where this leg started, where it connects, where the next one ends. An
# unknown country counts as crossing, which is the stricter reading and the
# same one docs/connection-search.md records.
def connection_minimum(dto, nxt):
    nxt_dep = (nxt or {}).get("departure") or {}
    nxt_arr = (nxt or {}).get("arrival") or {}
    origin = _country(dto, "departure")
    at_hub = _country(dto, "arrival") or nxt_dep.get("country") or None
    end = nxt_arr.get("country") or None
    crosses = None in (origin, at_hub, end) or origin != at_hub or at_hub != end
    return CONNECT_MIN_INTERNATIONAL if crosses else CONNECT_MIN_DOMESTIC


def _band(remaining, minimum):
    if remaining < minimum:
        return "will_miss"
    if remaining <= minimum + CONNECT_CUSHION:
        return "at_risk"
    return "comfortable"


# ── WHAT OF A BOARD ROW IS WORTH KEEPING ────────────────────────────────────
#
# A SUBSET, AND NAMED RATHER THAN THE WHOLE ROW. A board row carries fields the
# drawer has no use for, and this is provider data under a seven-day ceiling --
# see docs/connection-search.md -- so storing less of it for less time is the
# habit, not an optimisation.
#
# ARRIVAL TIMES ARE KEPT EVEN WHEN NULL, and the key is always present. A board
# row can name a destination airport and carry no arrival time at all; that row
# is still a real flight to the right place and belongs in the list. What it
# cannot do is be tested against a connection, so the absence has to survive to
# the surface that decides -- see Stage 2 -- rather than being defaulted here.
def _kept_row(r, t, now):
    return {
        "flight_number": r.get("flight_number"),
        "airline": r.get("airline"),
        "origin_iata": r.get("origin_iata"),
        "destination_iata": r.get("destination_iata"),
        "departure_scheduled_iso": r.get("departure_scheduled_iso"),
        "departure_scheduled": r.get("departure_scheduled"),
        "departure_timezone": r.get("departure_timezone"),
        "arrival_scheduled_iso": r.get("arrival_scheduled_iso"),
        "arrival_scheduled": r.get("arrival_scheduled"),
        "arrival_timezone": r.get("arrival_timezone"),
        # THE SAME THREE THE PUSH ALREADY RENDERS, so a row and the sentence
        # about it cannot come to disagree about which day it leaves.
        "time": _clock(t),
        "tz": _tz_label(r.get("departure_scheduled")),
        "day": _day_label(t, now),
        "date": t.date().isoformat(),
    }


# ── WOULD THIS REPLACEMENT STILL MAKE THE NEXT LEG ──────────────────────────
#
# THE ONE QUESTION THE DRAWER EXISTS TO ANSWER, and it is asked per row here so
# that no surface has to do arithmetic on a layover. Every row gets a verdict;
# nothing is silently dropped.
#
# FIVE VERDICTS, AND "unknown" IS NOT "no". A board row can name a destination
# airport and carry NO ARRIVAL TIME AT ALL -- see _kept_row -- and such a row is
# a real flight to the right place that simply cannot be tested. Calling that
# "will_miss" would hide a usable flight behind a number we never had; calling
# it "comfortable" would promise a connection on no evidence. It says unknown,
# stays out of the connection list, and stays in the list of flights to the
# destination.
#
#   None          there is no next leg -- a final leg, or a trip the server
#                 cannot pair. Every row is simply a flight to the destination.
#   "unknown"     no arrival time on the row.
#   "will_miss"   lands too late by the minimum.
#   "at_risk"     inside the cushion.
#   "comfortable" clears it.
#
# THE LAYOVER IS REPORTED IN MINUTES ALONGSIDE, because a band alone cannot be
# rendered as "2h 40m in Delhi" and the drawer should not re-derive it from two
# timestamps and get a different answer.
def classify_alternatives(dto, nxt, rows, now=None):
    """Each row, tagged with whether it still makes the next leg."""
    out = []
    minimum = connection_minimum(dto, nxt) if nxt else None
    leaves_at = _parse(((nxt or {}).get("departure") or {}).get("scheduled_iso")) if nxt else None
    hub = (((dto or {}).get("arrival") or {}).get("iata") or "").strip().upper()
    for r in rows or []:
        row = dict(r)
        lands = _parse(r.get("arrival_scheduled_iso"))
        # THE ROW MUST ACTUALLY GO TO THE HUB. True by construction -- the board
        # was fetched for this city pair -- and checked anyway, because a row
        # that does not is a row whose layover is meaningless rather than long.
        same_hub = (not hub) or (str(r.get("destination_iata") or "").strip().upper() == hub)
        if nxt is None or leaves_at is None or not same_hub:
            row["connects"] = None
            row["layover_minutes"] = None
        elif lands is None:
            row["connects"] = "unknown"
            row["layover_minutes"] = None
        else:
            gap = leaves_at - lands
            row["connects"] = _band(gap, minimum)
            row["layover_minutes"] = int(gap.total_seconds() // 60)
        row["minimum_minutes"] = int(minimum.total_seconds() // 60) if minimum else None
        out.append(row)
    return out


# ── AND THE WHOLE BLOCK THE DEVICE READS ────────────────────────────────────
#
# BUILT HERE RATHER THAN IN THE POLLER, because every judgement in it is this
# module's: which rows qualified, how old the search is, what a workable gap is.
# The poller's part is storage and it should stay that.
#
# PURE, and it costs nothing -- the search already ran, the next leg is already
# loaded from state. This is a reshaping of two things the caller holds.
#
# THE NEXT LEG IS SUMMARISED, NOT EMBEDDED. The drawer needs to name what the
# connection is FOR -- "to make ZZ902 at 14:05" -- and nothing more; the whole
# DTO is provider data with a seven-day ceiling on it, and a second copy of one
# inside another object is a second thing to expire.
def alternatives_block(dto, nxt, search, now):
    search = search or {}
    rows = classify_alternatives(dto, nxt, search.get("rows") or [], now)
    arr = (dto or {}).get("arrival") or {}
    nxt_dep = ((nxt or {}).get("departure") or {}) if nxt else {}
    return {
        "searched_at": search.get("searched_at"),
        "days_searched": int(search.get("days_searched") or 0),
        "done": bool(search.get("done")),
        "max_days": NEXT_MAX_DAYS,
        "origin": ((dto or {}).get("departure") or {}).get("iata"),
        "destination": arr.get("iata"),
        "next_leg": {
            "flight_number": (nxt or {}).get("flight_number"),
            "departure_iata": nxt_dep.get("iata"),
            "arrival_iata": ((nxt or {}).get("arrival") or {}).get("iata"),
            "departure_scheduled_iso": nxt_dep.get("scheduled_iso"),
            "departure_scheduled": nxt_dep.get("scheduled"),
        } if nxt else None,
        "rows": rows,
    }


def _search_next(facts, dto, now, search, lookup_next, days):
    """Walk the route board forward. Returns (found or None, search state).

    search state: {"from": iso of the cancelled departure, "next_day": the
    next local day to ask about, "days_searched": n, "done": bool,
    "found": the earliest row as the push renders it, "rows": up to
    NEXT_KEEP_ROWS of them for the drawer, "searched_at": when}."""
    dep = dto.get("departure") or {}
    origin, dest = facts["origin"]["iata"], facts["destination"]["iata"]
    sched = _parse(dep.get("scheduled_iso")) or now
    # WHERE THE DAY LOOP BEGINS: the travel date, or today if that is already
    # past. Unchanged, and deliberately not the row filter -- see NEXT_MIN_LEAD.
    anchor = max(sched, now)
    # WHAT A ROW HAS TO BEAT: reachable, not the dead flight's own schedule.
    earliest = now + NEXT_MIN_LEAD
    if search is None:
        search = {"from": _iso(anchor), "next_day": anchor.date().isoformat(),
                  "days_searched": 0, "done": False, "found": None,
                  "rows": [], "searched_at": None}
    search = dict(search)
    if lookup_next is None or not origin or not dest:
        return None, search
    own = str(facts.get("flight_number") or "").upper()
    for _ in range(days):
        if search["days_searched"] >= NEXT_MAX_DAYS:
            search["done"] = True
            break
        day = search["next_day"]
        try:
            rows = lookup_next(origin, dest, day) or []
        except Exception:
            # THE LOOKUP REFUSED -- the run's budget is spent, or the board is
            # down. That day has NOT been searched: stop here without advancing,
            # and the next poll asks about the same day.
            break
        search["days_searched"] += 1
        search["next_day"] = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
        # EVERY QUALIFYING ROW, IN TIME ORDER, rather than a running minimum.
        # fetch_route already returns a board sorted by departure, so the sort
        # here is a guarantee rather than a correction -- it costs nothing on an
        # already ordered list and means this function's output does not depend
        # on an ordering another module could change.
        good = []
        for r in rows:
            t = _parse(r.get("departure_scheduled_iso"))
            if t is None or t < earliest:
                continue
            if str(r.get("status") or "") == STATUS_CANCELLED:
                continue
            if str(r.get("flight_number") or "").upper() == own and t.date() == anchor.date():
                continue
            good.append((t, r))
        good.sort(key=lambda pair: pair[0])
        if good:
            search["rows"] = [_kept_row(r, t, now) for t, r in good[:NEXT_KEEP_ROWS]]
            search["searched_at"] = _iso(now)
            t, r = good[0]
            found = {"flight_number": r.get("flight_number"), "airline": r.get("airline"),
                     "time": _clock(t), "tz": _tz_label(r.get("departure_scheduled")),
                     "day": _day_label(t, now), "date": t.date().isoformat(),
                     "iso": r.get("departure_scheduled_iso")}
            search["done"] = True
            search["found"] = found
            return found, search
    if search["days_searched"] >= NEXT_MAX_DAYS:
        search["done"] = True
        # NOTHING FOUND IS ALSO A RESULT, AND IT IS DATED. The drawer has to be
        # able to say "we looked, an hour ago, and there was nothing" rather
        # than showing an empty list that could equally mean nobody has asked.
        search["searched_at"] = _iso(now)
    return None, search


# ── THE SENTENCE, WRITTEN FOR ONE READER ────────────────────────────────────
def subject(msg, owned=True, same_city=1, same_time=1):
    """The thing the message is about, for THIS reader.

    owned: the reader is on the flight (True) or meeting it (False). None is
    treated as on it, which is what the app registers by default.
    same_city: how many flights to this city the reader watches that day.
    same_time: of those, how many share this scheduled time."""
    city_to = (msg.get("destination") or {}).get("city") or (msg.get("destination") or {}).get("iata") or "your destination"
    city_from = (msg.get("origin") or {}).get("city") or (msg.get("origin") or {}).get("iata") or "the origin"
    when = " ".join((msg.get("scheduled_departure") or "").split()[:2])  # '9:30 PM', no zone
    airline = msg.get("airline") or ""
    parts = []
    if same_city > 1 and when:
        parts.append(when)
    if same_time > 1 and airline:
        parts.append(airline)
    qualifier = (" ".join(parts) + " ") if parts else ""
    if owned is False:
        return "The %sflight from %s" % (qualifier, city_from)
    return "Your %sflight to %s" % (qualifier, city_to)


def render(msg, owned=True, same_city=1, same_time=1):
    """One sentence or two. Facts in, words out; nothing here decides."""
    s = subject(msg, owned, same_city, same_time)
    v = msg.get("values") or {}
    k = msg.get("kind")
    city_to = (msg.get("destination") or {}).get("city") or "your destination"
    city_from = (msg.get("origin") or {}).get("city") or "the origin"
    tz = (" " + v["tz"]) if v.get("tz") else ""

    if k == CANCELLED:
        nxt = v.get("next")
        if nxt:
            return "%s is cancelled. The next one leaves %s at %s, %s %s." % (
                s, nxt.get("day"), nxt.get("time"), nxt.get("airline") or "", nxt.get("flight_number") or "")
        if v.get("none_within_days"):
            # NOT "AS FAR AS THE SCHEDULE REACHES", WHICH STOPPED BEING TRUE.
            # That clause was honest while the search ran to the timetable's own
            # sixty-day limit; it now stops at a week, and saying the schedule
            # ends there would be the app inventing an absence. It says what it
            # did instead: it looked a week ahead. The week is NEXT_MAX_DAYS in
            # words -- change one, change both, and the same sentence again
            # under NEXT_FLIGHT below.
            return "%s is cancelled. Nothing else on this route in the next week." % s
        return "%s is cancelled. Terminal is looking for the next departure and will tell you." % s
    if k == NEXT_FLIGHT:
        nxt = v.get("next")
        if nxt:
            return "The next flight to %s leaves %s at %s, %s %s." % (
                city_to, nxt.get("day"), nxt.get("time"), nxt.get("airline") or "", nxt.get("flight_number") or "")
        # THE SAME SENTENCE, PLUS THE CITY. This one arrives on its own, hours
        # after the cancellation it follows, so it cannot lean on a subject line
        # the reader is still looking at -- "this route" alone would not say
        # which. See the cancelled branch for why the schedule is no longer
        # claimed to end here.
        return "Nothing else to %s on this route in the next week." % city_to
    if k == CANCEL_WITHDRAWN:
        return "%s is no longer showing as cancelled. Scheduled %s from %s." % (s, v.get("scheduled"), city_from)
    if k == GATE:
        if v.get("was"):
            return "%s has moved to gate %s, was %s." % (s, v["gate"], v["was"])
        term = (", Terminal %s" % v["terminal"]) if v.get("terminal") else ""
        return "%s departs from gate %s%s." % (s, v["gate"], term)
    if k == GATE_CAP:
        return "%s's gate keeps changing. Terminal will show the current one when you open it." % s
    if k == TERMINAL:
        return "%s now departs from Terminal %s, not Terminal %s." % (s, v["terminal"], v["was"])
    if k == DELAY:
        d = _duration(timedelta(minutes=v.get("delay_min") or 0))
        if v.get("change") == "more":
            return "%s is delayed further, now %s. Expected %s%s." % (s, d, v.get("expected"), tz)
        if v.get("change") == "less":
            return "%s's delay has shortened to %s. Expected %s%s." % (s, d, v.get("expected"), tz)
        return "%s is delayed %s. Now expected %s%s from %s." % (s, d, v.get("expected"), tz, city_from)
    if k == ON_TIME:
        return "%s is back on schedule, %s from %s." % (s, v.get("scheduled"), city_from)
    if k == DEPARTED:
        if v.get("due"):
            return "%s has left %s. Due around %s%s." % (s, city_from, v["due"], tz)
        return "%s has left %s." % (s, city_from)
    if k == ARRIVAL_MOVED:
        by = v.get("later_by") or 0
        tail = (", %s later" % _duration(timedelta(minutes=by))) if by > 0 else (", %s earlier" % _duration(timedelta(minutes=-by)) if by < 0 else "")
        return "%s is now due around %s%s%s." % (s, v.get("due"), tz, tail)
    if k == ARRIVAL_TERMINAL:
        return "%s now arrives at Terminal %s, not Terminal %s." % (s, v["terminal"], v["was"])
    if k == LANDED:
        where = (", though not at %s" % city_to) if v.get("elsewhere") else ""
        t = (", %s%s" % (v["time"], tz)) if v.get("time") else ""
        belt = (" Bags on belt %s." % v["belt"]) if v.get("belt") else ""
        return "%s has landed%s%s.%s" % (s, where, t, belt)
    if k == BELT:
        return "%s: bags on belt %s." % (s, v.get("belt"))
    if k == DIVERTED:
        return "%s has been diverted. Terminal does not yet know where it landed, and will say when it does." % s
    if k == CONNECTION:
        nxt = v.get("next") or {}
        onward = nxt.get("flight_number") or "your next flight"
        left = _duration(timedelta(minutes=v.get("remaining_min") or 0))
        usual = _duration(timedelta(minutes=v.get("minimum_min") or 0))
        # ── THE HUB IS THIS LEG'S DESTINATION, AND THE SUBJECT MAY ALREADY
        # ── HAVE SAID IT ───────────────────────────────────────────────────
        #
        # subject() names the city a flight is going TO -- "your flight to
        # Bangalore" -- and on a connection that city IS the hub, which gave
        # "your flight to Bangalore ... in Bangalore". So the clause is dropped
        # whenever the subject has already placed the reader, which for an
        # owned flight with a known destination city is every time.
        #
        # IT IS KEPT WHEN THE SUBJECT COULD NOT NAME THE PLACE. A DTO whose
        # arrival city is absent gives a subject with no city in it, and then
        # this is the only thing in the sentence that says where the reader
        # will be standing. Comparing the two strings rather than assuming
        # either case is what covers both.
        where = v.get("hub") or ""
        at = (" in %s" % where) if where and where.lower() not in s.lower() else ""
        # ── NO SENTENCE SENDS ANYBODY TO THE AIRLINE ────────────────────────
        #
        # THIS ONE DID, AND IT SHOULD NOT HAVE. "Check with the airline" was on
        # the end of the missed-connection line, and it is the one instruction
        # this app has a standing rule against: the person is already holding
        # the only device that knows, and telling them to go and ask somebody
        # else is an admission dressed as advice. test_notify has asserted the
        # rule since the ledger tests were written -- see "no sentence sends
        # anyone to the airline" -- and that check was scoped to one message
        # set, so this slipped past it. It is not scoped any more.
        #
        # WHAT REPLACES IT IS NOTHING. The sentence already says the flight is
        # late enough to miss the next one and how little is between them,
        # which is the whole of what is known. The help that belongs here is
        # the rebooking work that has not been built; until it is, the honest
        # end of this sentence is a full stop.
        if v.get("band") == "will_miss":
            return ("%s is running late enough to miss %s%s -- about %s between them, "
                    "where %s is the usual minimum."
                    % (s, onward, at, left, usual))
        return ("%s is running late enough to put %s%s at risk -- about %s between them, "
                "where %s is the usual minimum." % (s, onward, at, left, usual))
    return "%s has an update." % s


def deep_link(msg):
    """What a tap opens. A cancellation opens the route list, earliest first;
    everything else opens the flight."""
    if msg.get("kind") in (CANCELLED, NEXT_FLIGHT):
        nxt = (msg.get("values") or {}).get("next") or {}
        return {"screen": "search", "from": (msg.get("origin") or {}).get("iata"),
                "to": (msg.get("destination") or {}).get("iata"),
                "date": nxt.get("date") or msg.get("flight_date"), "sort": "earliest"}
    # A CONNECTION WARNING OPENS THE FLIGHT AT RISK, which is the NEXT leg and
    # not the delayed one. The delayed leg is the cause and the person can
    # already see it; the onward flight is the one they may have to do
    # something about. Falls back to this leg if the next carries no number.
    if msg.get("kind") == CONNECTION:
        nxt = (msg.get("values") or {}).get("next") or {}
        if nxt.get("flight_number"):
            return {"screen": "flight", "flight_number": nxt.get("flight_number"),
                    "date": nxt.get("date") or msg.get("flight_date")}
    return {"screen": "flight", "flight_number": msg.get("flight_number"), "date": msg.get("flight_date")}
