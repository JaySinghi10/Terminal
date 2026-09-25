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
depends on who is reading it. "Your flight's gate changed" is right for the
person on it; "The gate changed" is right for the person meeting it. See
render(), and subject() for the title over it.

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
import re
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

# ── HOW LONG A SENT MESSAGE IS WORTH HOLDING FOR A PHONE THAT IS OFFLINE ────
#
# EACH KIND LIVES UNTIL THE MOMENT IT STOPS BEING TRUE, measured from the
# flight's own times; dispatch hands Expo whatever is left of that as the
# message's ttl. It was one hour for everything, so anything sent during a long
# flight had expired before the passenger's phone came back on.
#
# SO THE SAME KIND CAN BE LONG OR SHORT. A gate is worth having until its flight
# leaves: for the next leg that is hours after the passenger lands, for a flight
# boarding now it is minutes. The rule names the event rather than a number.
#
# AND AN OFFLINE iPHONE KEEPS ONE. Apple stores a single notification per app
# for a device it cannot reach, chosen by Apple and not necessarily the newest
# (Apple DTS, February 2025). A longer life cannot deliver a backlog; it can
# stop the one message that survives from having expired. That is why dispatch
# also gives messages that supersede each other a collapse id, and why the
# landing summary restates everything the next step needs.
EXPIRY_GRACE = timedelta(minutes=15)
EXPIRY_LONG = timedelta(hours=24)
EXPIRY_DIVERTED = timedelta(hours=6)
EXPIRY_BELT = timedelta(minutes=45)
EXPIRY_AFTER_LANDING = timedelta(hours=2)
# About when the flight leaves, or about when it lands.
UNTIL_DEPARTURE = {GATE, GATE_CAP, TERMINAL, DELAY, ON_TIME, CANCEL_WITHDRAWN}
UNTIL_ARRIVAL = {DEPARTED, ARRIVAL_MOVED, ARRIVAL_TERMINAL}

# ── WHERE CHECKED BAGS COME OFF ─────────────────────────────────────────────
#
# AT THE END OF THE JOURNEY, NOT AT A CONNECTION. Bags on a connecting itinerary
# are checked through to the final destination, so the belt at the hub is not
# where they are, and printing it sends the passenger to the wrong hall. The
# exception is the first airport in the United States on the way in from
# abroad, where bags are collected for customs and checked again. The app's
# bagEligible draws the same line; change one, change both.
BAGS_RECLAIMED_ON_ENTRY = {"US"}

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
def decide(ns, dto, landing, now, lookup_next=None, connection=None, trace=None):
    """(new_state, messages). dto is the CURRENT record; landing the current
    landing answer or None; lookup_next(origin, dest, day) -> rows, or None
    when the caller has no budget for it this poll.

    connection is the DTO of the leg this one connects INTO, or None when there
    is no next leg or the caller could not resolve one. It is read-only and
    costs nothing: the caller has already loaded it from state. See
    connection_band.

    Pure over its inputs apart from lookup_next, which is the one call that
    leaves the process, and it is only made on a cancellation.

    trace, WHEN GIVEN, IS APPENDED TO FOR EVERY MESSAGE DECIDED AGAINST -- a key
    already sent, or the per-flight rate floor. emit used to return False and say
    nothing, which is right for a push and useless to anybody asking afterwards
    why one never arrived. None, the default, changes nothing at all. See
    diag.py, the only caller that passes one."""
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

    def emit(kind, values, deliver_after=None, key_value="", expires=None):
        k = _key(facts, kind, key_value)
        if k in ns["keys"]:
            if trace is not None:
                trace.append({"kind": kind, "reason": "already sent"})
            return False
        last = _parse(ns.get("last_msg_at"))
        if kind not in FLOOR_EXEMPT and last is not None and now - last < FLIGHT_FLOOR:
            if trace is not None:
                trace.append({"kind": kind, "reason": "rate floor"})
            return False
        msg = dict(facts)
        # UNTIL WHEN IT IS WORTH HOLDING FOR AN OFFLINE PHONE, decided here where
        # the record is, and read by dispatch as the push's ttl. See expiry.
        until = expires if expires is not None else expiry(kind, dto, now, onward=connection)
        msg.update({"key": k, "kind": kind, "at": _iso(now),
                    "deliver_after": _iso(deliver_after) if deliver_after else None,
                    "expires_at": _iso(until) if until else None,
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
    #
    # AND ON THE LANDING POLL THE SUMMARY SAYS IT INSTEAD. The band is recorded
    # as told either way, but the passenger gets one message for landing, and
    # the summary below carries the connection's band in it -- two pushes a
    # minute apart would compete for the one slot an offline phone keeps.
    landing_now = landed and "landed" not in ns["notified"]
    if connection is not None and status not in (STATUS_CANCELLED, STATUS_DIVERTED):
        judged = connection_band(dto, connection, now)
        if judged is not None:
            band, remaining, minimum = judged
            told = ns["notified"].get("connection_band") or "comfortable"
            if CONNECT_BANDS.index(band) > CONNECT_BANDS.index(told):
                ns["notified"]["connection_band"] = band
                nxt_dep = (connection.get("departure") or {})
                if not landing_now:
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

    # WHETHER THIS LEG FEEDS ANOTHER, which the summary and the belt both ask.
    # connection_band is the test, so neither can name a leg the warning would
    # not have treated as a connection.
    connecting = connection is not None and connection_band(dto, connection, now) is not None

    # ── LANDED ── once, from the landing feed only
    #
    # THE ONE MESSAGE FOR THE PASSENGER'S NEXT STEP. It says when the aircraft
    # came down and how early or late -- the touchdown against the scheduled
    # arrival, the figure the app's cards print -- then either the belt, at the
    # end of a journey, or the next leg: its expected departure and its gate, or
    # that it is cancelled, and the connection's band when that is at risk.
    #
    # IT IS THE LAST THING SENT BEFORE MOST PHONES COME BACK ON, and an offline
    # iPhone keeps one notification: so it restates the next leg's state rather
    # than trusting that the gate or cancellation sent mid-flight survived.
    if landed and "landed" not in ns["notified"]:
        ns["notified"]["landed"] = landing.get("landed_utc")
        when = _parse(landing.get("landed_utc"))
        local = _to_zone(when, arr.get("timezone"))
        nxt = _next_step(dto, connection, now) if connecting else None
        # THE BELT ONLY WHERE THE BAGS COME OFF. See BAGS_RECLAIMED_ON_ENTRY.
        belt = arr.get("baggage") if _bags_claimed_here(dto, connecting) else None
        if belt:
            ns["notified"]["belt"] = belt
            ns["counts"][BELT] = int(ns["counts"].get(BELT, 0)) + 1
        emit(LANDED, {"time": _clock(local) if local else None,
                      "tz": _tz_label(arr.get("scheduled")),
                      "offset_min": _minutes(when - sched_arr) if when and sched_arr else None,
                      "belt": belt,
                      "elsewhere": bool(landing.get("diverted_to")),
                      # WHERE IT CAME DOWN INSTEAD, so the sentence can name
                      # both ends of the change: "landed at HYD instead of Mumbai".
                      "diverted_to": landing.get("diverted_to"),
                      "next": nxt},
             expires=expiry(LANDED, dto, now, onward=connection if nxt else None, landed_at=when))
        return ns, out

    # ── BELT ── only after landing, inside the window, and only where the bags
    # come off: a belt at a connection is not where a through-checked bag is.
    if "landed" in ns["notified"]:
        when = _parse(ns["notified"].get("landed"))
        belt = arr.get("baggage")
        if (belt and belt != ns["notified"].get("belt") and when is not None
                and _bags_claimed_here(dto, connecting)
                and now - when <= BELT_WINDOW
                and int(ns["counts"].get(BELT, 0)) < BELT_CAP_COUNT
                and _settled(ns, "belt", belt)):
            # THE BELT IT MOVED FROM, when one was already told.
            was = ns["notified"].get("belt")
            ns["notified"]["belt"] = belt
            emit(BELT, {"belt": belt, "was": was}, key_value=belt)
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
                # THE LAST GATE MESSAGE, AND IT STILL NAMES BOTH GATES.
                emit(GATE_CAP, {"gate": gate, "was": ns["notified"].get("gate")})
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


# ── UNTIL WHEN A SENT MESSAGE IS WORTH HOLDING ──────────────────────────────
def _expected(movement):
    """The instant a movement happens or is due: actual, then estimated, then
    scheduled -- the precedence the poller tiers on and the app draws with."""
    m = movement or {}
    return (_parse(m.get("actual_iso")) or _parse(m.get("estimated_iso"))
            or _parse(m.get("scheduled_iso")))


def expiry(kind, dto, now, onward=None, landed_at=None):
    """When a message of this kind stops being worth delivering, or None when
    there is nothing to measure it from. See EXPIRY_GRACE for the rule; dispatch
    applies the floor and the ceiling, and an hour where this says nothing.

    onward is the leg the passenger connects into: the one a connection warning
    is about, and the one a landing summary names. A summary that names none is
    worth two hours after the landing."""
    if kind in UNTIL_DEPARTURE:
        t = _expected((dto or {}).get("departure"))
        return t + EXPIRY_GRACE if t else None
    if kind in UNTIL_ARRIVAL:
        t = _expected((dto or {}).get("arrival"))
        return t + EXPIRY_GRACE if t else None
    if kind in (CANCELLED, NEXT_FLIGHT):
        return now + EXPIRY_LONG
    if kind == DIVERTED:
        return now + EXPIRY_DIVERTED
    if kind == BELT:
        return now + EXPIRY_BELT
    if kind == CONNECTION:
        return _expected((onward or {}).get("departure"))
    if kind == LANDED:
        leaves = _expected((onward or {}).get("departure")) if onward else None
        return leaves or (landed_at or now) + EXPIRY_AFTER_LANDING
    return None


# ── THE LANDING SUMMARY'S TWO QUESTIONS ─────────────────────────────────────
def _bags_claimed_here(dto, connecting):
    """Whether checked bags come off at this leg's arrival. See
    BAGS_RECLAIMED_ON_ENTRY: always at the end of a journey, and at a
    connection only on the way into a country that reclaims them."""
    if not connecting:
        return True
    into = _country(dto, "arrival")
    came_from = _country(dto, "departure")
    return into in BAGS_RECLAIMED_ON_ENTRY and came_from is not None and came_from != into


def _next_step(dto, onward, now):
    """The leg the passenger goes on to, as the landing summary names it, or
    None when there is no connection -- the same test the warning uses, so the
    summary never names a flight connection_band would not.

    ITS EXPECTED DEPARTURE, NOT ITS TIMETABLE. The warning measures against the
    timetable on purpose; the summary is telling somebody when to be at a gate,
    and that is the revised time."""
    judged = connection_band(dto, onward, now)
    if judged is None:
        return None
    band = judged[0]
    ndep = (onward or {}).get("departure") or {}
    leaves = _parse(ndep.get("estimated_iso")) or _parse(ndep.get("scheduled_iso"))
    return {
        "flight_number": onward.get("flight_number"),
        "time": _clock(leaves) if leaves else None,
        # ITS OWN ZONE, which is the airport just landed at: every clock in a
        # push carries one.
        "tz": _tz_label(ndep.get("scheduled")),
        "gate": ndep.get("gate") or None,
        "terminal": ndep.get("terminal") or None,
        "cancelled": str(onward.get("status") or "").lower() == STATUS_CANCELLED,
        "band": band if band != "comfortable" else None,
    }


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
#
# THE TITLE IS THE ROUTE AND THE FLIGHT; THE BODY IS ONE SHORT LINE OF NEWS,
# said to whoever is reading it:
#
#     Amsterdam → Mumbai · KL877
#     Your flight's gate changed from E2 to E6
#
# THE SAME TITLE FOR EVERY READER. A route says which flight to the person on
# it and to the person meeting it alike, so it no longer turns round for the
# second the way "To London" became "From New York". City names when they fit
# on one lock-screen line, airport codes when they would be cut off -- see
# TITLE_MAX -- and never one of each.
#
# THE BODY IS PERSONAL FOR THE TRAVELLER AND PLAIN FOR SOMEBODY MEETING THE
# FLIGHT: "Your flight's gate changed from E2 to E6" against "The gate changed
# from E2 to E6". It names the old value wherever something changed -- a gate,
# a terminal, a belt, the airport it came down at instead -- EXCEPT A TIME:
# "delayed 25 min" already says what moved, so a delay says only when it now
# leaves.
#
# EVERY CLOCK IS 24-HOUR AND CARRIES ITS AIRPORT'S ZONE, as the app prints
# them: "21:15 CEST". The values keep the record's own 12-hour text, which the
# drawer's rows also read, and render converts -- so a message queued before
# this wording reads the same way as one written after it.
#
# NO BODY SENDS ANYBODY TO THE AIRLINE. The person is already holding the only
# device that knows, and telling them to go and ask somebody else is an
# admission dressed as advice. test_notify asserts it across every message.

# ── HOW LONG A TITLE CAN BE AND STILL FIT ───────────────────────────────────
#
# TWENTY-SIX CHARACTERS, which is "Amsterdam → Mumbai · KL877" exactly, and
# about what the narrowest iPhones (SE, mini) show of a bold title beside its
# timestamp. "San Francisco → London · BA286" at thirty is cut off there, so it
# goes out as "SFO → LHR · BA286". A count and not a measured width, so it is
# the same answer on the server, in the tests and in devFixtures' copy.
TITLE_MAX = 26


def subject(msg, owned=True, same_city=1, same_time=1):
    """The title: the route and the number, "Amsterdam → Mumbai · KL877", or
    by airport code, "SFO → AMS · KL606", when the cities would not fit on one
    lock-screen line. The same for every reader.

    owned, same_city and same_time are still passed by dispatch and no longer
    read: the route and the number separate every flight they used to."""
    number = str(msg.get("flight_number") or "").strip()
    frm, to = msg.get("origin") or {}, msg.get("destination") or {}

    def titled(a, b):
        route = "%s → %s" % (a, b) if a and b else ""
        return " · ".join(p for p in (route, number) if p)

    if frm.get("city") and to.get("city"):
        by_city = titled(frm["city"], to["city"])
        if len(by_city) <= TITLE_MAX:
            return by_city
    by_code = titled(frm.get("iata") or frm.get("city"), to.get("iata") or to.get("city"))
    return by_code or "Your flight"


_CLOCK_12 = re.compile(r"\b(\d{1,2}):(\d{2})\s?([AP])M\b", re.IGNORECASE)


def _24h(text):
    """'21:15 CEST' from '9:15 PM CEST': every clock in the text 24-hour and
    zero-padded, as the app prints them. Anything else passes unchanged."""
    def to_24(m):
        hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "P" else 0)
        return "%02d:%s" % (hour, m.group(2))
    return _CLOCK_12.sub(to_24, str(text or ""))


def _at(clock, tz=""):
    """A clock with its zone, '21:15 CEST'; '' when there is no clock."""
    if not clock:
        return ""
    return "%s %s" % (_24h(clock), tz) if tz else _24h(clock)


def _when(nxt):
    """The next flight's day and clock: "today at 17:05 PDT", "tomorrow at
    ...", "on Sunday at ...", "on 25 Sep at ..."."""
    day = nxt.get("day") or ""
    day = day if day in ("today", "tomorrow") or not day else "on %s" % day
    clock = "at %s" % _at(nxt["time"], nxt.get("tz")) if nxt.get("time") else ""
    return " ".join(p for p in (day, clock) if p)


def _early_or_late(offset_min):
    """How the landing did: 38 min early, 12 min late, on time at the minute."""
    if offset_min == 0:
        return "on time"
    return "%s %s" % (_duration(timedelta(minutes=offset_min)),
                      "late" if offset_min > 0 else "early")


def _next_words(nxt, tz=""):
    """The landing summary's last clause, for the passenger: "next is LX325 at
    11:50 BST from gate A12", the terminal while no gate is assigned, that it
    is cancelled, and the connection's band when it is at risk. A summary
    written before the next leg carried its zone borrows the landing's, which
    is the same airport's."""
    number = nxt.get("flight_number")
    if nxt.get("cancelled"):
        return "next flight %s is cancelled" % number if number else "next flight is cancelled"
    out = "next is %s" % number if number else "next flight"
    if nxt.get("time"):
        out += " at %s" % _at(nxt["time"], nxt.get("tz") or tz)
    if nxt.get("gate"):
        out += " from gate %s" % nxt["gate"]
    elif nxt.get("terminal"):
        out += " from Terminal %s" % nxt["terminal"]
    if nxt.get("band") == "will_miss":
        out += ", connection won't hold"
    elif nxt.get("band") == "at_risk":
        out += ", connection at risk"
    return out


def render(msg, owned=True, same_city=1, same_time=1):
    """The body: one short line, personal for the traveller -- "Your flight's
    gate changed from E2 to E6" -- and plain for somebody meeting the flight --
    "The gate changed from E2 to E6". Facts in, words out; nothing here decides.

    owned: the reader is on the flight (True) or meeting it (False). None is
    treated as on it, which is what the app registers by default."""
    v = msg.get("values") or {}
    k = msg.get("kind")
    yours = owned is not False
    flight = "Your flight" if yours else "The flight"
    gate_of = "Your flight's gate" if yours else "The gate"
    bags = "Your bags" if yours else "The bags"
    dest = msg.get("destination") or {}
    city_to = dest.get("city") or dest.get("iata") or ""
    tz = v.get("tz") or ""

    if k == CANCELLED:
        nxt = v.get("next")
        if nxt:
            # THE DAY IS ALWAYS SAID, "today" included: a next flight tomorrow
            # read as a clock alone would be a time somebody could miss by a day.
            if nxt.get("flight_number"):
                return "%s is cancelled, next is %s %s" % (flight, nxt["flight_number"], _when(nxt))
            return "%s is cancelled, the next flight leaves %s" % (flight, _when(nxt))
        if v.get("none_within_days"):
            # A WEEK, NOT "AS FAR AS THE SCHEDULE REACHES": the search looks
            # NEXT_MAX_DAYS ahead and no further, so that is all the sentence
            # claims. Change one, change both, and NEXT_FLIGHT's below.
            return "%s is cancelled, no other flight this week" % flight
        return "%s is cancelled, finding the next flight" % flight
    if k == NEXT_FLIGHT:
        # IT ARRIVES ON ITS OWN, hours after the cancellation it follows, so it
        # says again what it follows. The title names the route.
        nxt = v.get("next")
        if nxt:
            if nxt.get("flight_number"):
                return "%s was cancelled, next is %s %s" % (flight, nxt["flight_number"], _when(nxt))
            return "%s was cancelled, the next flight leaves %s" % (flight, _when(nxt))
        return "%s was cancelled, no other flight this week" % flight
    if k == CANCEL_WITHDRAWN:
        if v.get("scheduled"):
            return "%s is no longer cancelled and leaves at %s" % (flight, _24h(v["scheduled"]))
        return "%s is no longer cancelled" % flight
    if k == GATE:
        if v.get("was"):
            return "%s changed from %s to %s" % (gate_of, v["was"], v["gate"])
        if v.get("terminal"):
            return "%s is %s, in Terminal %s" % (gate_of, v["gate"], v["terminal"])
        return "%s is %s" % (gate_of, v["gate"])
    if k == GATE_CAP:
        # THE LAST GATE MESSAGE THIS FLIGHT GETS -- see GATE_CAP_COUNT. One
        # queued before it carried the gates says only that it changed again.
        if v.get("gate") and v.get("was"):
            return "%s changed again, from %s to %s" % (gate_of, v["was"], v["gate"])
        if v.get("gate"):
            return "%s changed again, to %s" % (gate_of, v["gate"])
        return "%s changed again" % gate_of
    if k == TERMINAL:
        out = "%s now leaves from Terminal %s" % (flight, v["terminal"])
        return out + (" instead of Terminal %s" % v["was"] if v.get("was") else "")
    if k in (DELAY, ON_TIME):
        # NO OLD TIME. The delay figure already says what changed; the one
        # thing to add is when it now leaves.
        if k == ON_TIME:
            what, leaves = "%s is back on time" % flight, _24h(v.get("scheduled"))
        else:
            leaves = _at(v.get("expected"), tz)
            if v.get("change") == "more":
                what = "%s is delayed again" % flight
            elif v.get("change") == "less":
                what = "%s's delay is shorter" % flight
            else:
                what = "%s is delayed %s" % (flight, _duration(timedelta(minutes=v.get("delay_min") or 0)))
        return "%s, now leaves at %s" % (what, leaves) if leaves else what
    if k == DEPARTED:
        if v.get("due"):
            return "%s took off and lands around %s" % (flight, _at(v["due"], tz))
        return "%s took off" % flight
    if k == ARRIVAL_MOVED:
        if v.get("due"):
            return "%s now lands around %s" % (flight, _at(v["due"], tz))
        return "%s has a new landing time" % flight
    if k == ARRIVAL_TERMINAL:
        out = "%s now arrives at Terminal %s" % (flight, v["terminal"])
        return out + (" instead of Terminal %s" % v["was"] if v.get("was") else "")
    if k == LANDED:
        if v.get("elsewhere"):
            if not city_to:
                return "%s landed somewhere else" % flight
            if v.get("diverted_to"):
                return "%s landed at %s instead of %s" % (flight, v["diverted_to"], city_to)
            return "%s landed, but not in %s" % (flight, city_to)
        parts = ["%s landed at %s" % (flight, _at(v["time"], tz)) if v.get("time") else "%s landed" % flight]
        # HOW EARLY OR LATE, the touchdown against the timetable. A message
        # written before the figure existed has none and reads without it.
        off = v.get("offset_min")
        if isinstance(off, int):
            parts.append(_early_or_late(off))
        if v.get("belt"):
            parts.append("bags on belt %s" % v["belt"])
        # THE NEXT LEG IS THE PASSENGER'S. Somebody meeting the flight is not
        # taking it, and hears the landing and the belt.
        nxt = v.get("next") if yours else None
        if nxt:
            parts.append(_next_words(nxt, tz))
        return ", ".join(parts)
    if k == BELT:
        if v.get("was") and v["was"] != v.get("belt"):
            return "%s are now on belt %s instead of belt %s" % (bags, v.get("belt"), v["was"])
        return "%s are on belt %s" % (bags, v.get("belt"))
    if k == DIVERTED:
        away = " from %s" % city_to if city_to else ""
        return "%s has been diverted%s, landing airport not known yet" % (flight, away)
    if k == CONNECTION:
        # THE ONWARD FLIGHT AND THE HUB, and no minutes: the layover is on the
        # trip screen the tap opens -- see deep_link.
        conn = "Your connection" if yours else "The connection"
        onward = (v.get("next") or {}).get("flight_number")
        to = " to %s" % onward if onward else ""
        where = " in %s" % v["hub"] if v.get("hub") else ""
        if v.get("band") == "will_miss":
            return "%s%s%s won't hold" % (conn, to, where)
        return "%s%s%s is at risk" % (conn, to, where)
    return "%s was updated" % flight


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
