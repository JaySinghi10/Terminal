"""The notification rules, offline. Replays the one real ledger the poller has
written (6E6188, 7 Sep 2026) and the case that has to be right: seven gate
changes in twelve hours, seventeen hours before departure.
"""
import copy
import sys
from datetime import datetime, timedelta, timezone

import notify as N

PASS = FAIL = 0


def check(label, cond, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % label)
    else:
        FAIL += 1
        print("  FAIL %s   -> %r" % (label, detail))


IST = timezone(timedelta(hours=5, minutes=30))


def T(h, m, day=7):
    return datetime(2026, 9, day, h, m, tzinfo=IST)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M%z")[:-2] + ":" + dt.strftime("%z")[-2:]


def clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0") + " IST"


def dto(status="scheduled", gate=None, term="2", est=None, act=None, arr_est=None, arr_act=None, belt=None,
        sched=T(21, 30), arr_sched=T(23, 25), arr_term="1"):
    return {
        "flight_number": "6E6188", "flight_date": "2026-09-07", "airline": "IndiGo", "status": status,
        "departure": {"airport": "Mumbai Chhatrapati Shivaji", "city": "Mumbai", "iata": "BOM",
                      "terminal": term, "gate": gate, "timezone": "Asia/Kolkata",
                      "scheduled": clock(sched), "scheduled_iso": iso(sched),
                      "estimated": clock(est) if est else None, "estimated_iso": iso(est) if est else None,
                      "actual": clock(act) if act else None, "actual_iso": iso(act) if act else None},
        "arrival": {"airport": "Bangalore Bengaluru", "city": "Bangalore", "iata": "BLR",
                    "terminal": arr_term, "gate": None, "baggage": belt, "timezone": "Asia/Kolkata",
                    "scheduled": clock(arr_sched), "scheduled_iso": iso(arr_sched),
                    "estimated": clock(arr_est) if arr_est else None, "estimated_iso": iso(arr_est) if arr_est else None,
                    "actual": clock(arr_act) if arr_act else None, "actual_iso": iso(arr_act) if arr_act else None},
    }


def run(steps, ns=None, lookup=None):
    """steps: [(now, dto, landing)] -> (final ns, [(now, msg)])"""
    got = []
    for now, d, landing in steps:
        ns, msgs = N.decide(ns, d, landing, now, lookup_next=lookup)
        for m in msgs:
            got.append((now, m))
    return ns, got


def kinds(got):
    return [m["kind"] for _, m in got]


# ── THE REAL LEDGER, REPLAYED ───────────────────────────────────────────────
# The four entries the poller wrote for 6E6188 on 7 Sep, rebuilt as the record
# each poll saw. The poller first saw the flight already "departed" at 21:30
# (which was a pushback estimate wearing the wrong label), then the actual was
# revised to 22:23, the arrival estimate moved, the feed reported the landing,
# and the provider caught up. Belt 2 was on the record at the landing poll.
print("-- the 6E6188 ledger, replayed --")
landing = {"outcome": "landed", "landed_utc": "2026-09-07T18:12:17", "diverted_to": None}
steps = [
    (T(22, 30), dto("active", gate="87A", act=T(21, 30), arr_est=T(23, 25)), None),           # first sight
    (T(23, 2), dto("active", gate="87A", act=T(22, 23), arr_est=T(23, 25)), None),            # 17:32Z actual revised
    (T(23, 4), dto("active", gate="87A", act=T(22, 23), arr_est=T(23, 25)), None),            # held
    (T(23, 38), dto("active", gate="87A", act=T(22, 23), arr_est=T(23, 38)), None),           # 18:08Z est +13
    (T(23, 44), dto("active", gate="87A", act=T(22, 23), arr_est=T(23, 38), belt="2"), landing),  # 18:14Z landed
    (T(23, 58), dto("landed", gate="87A", act=T(22, 23), arr_act=T(23, 41), belt="2"), landing),  # 18:28Z caught up
    (T(0, 10, day=8), dto("landed", gate="87A", act=T(22, 23), arr_act=T(23, 41), belt="2"), landing),
]
ns, got = run(steps)
# ONE MESSAGE. The poller first saw this flight after it had left, and first
# sight is not a change: the person was not told "departed" for a departure
# that happened before they were watching. The revised actual, the 13-minute
# arrival slip and the provider catching up are all swallowed.
check("one message and only one: landed", kinds(got) == [N.LANDED], kinds(got))
check("first sight said nothing, and the landing came at the landing poll", got[0][0] == T(23, 44), got[0][0] if got else None)
check("the 13-minute arrival slip was swallowed (under fifteen)", N.ARRIVAL_MOVED not in kinds(got))
check("the revised actual was swallowed (no time was ever claimed)", N.DEPARTED not in kinds(got))
landed_text = N.render(got[0][1])
check("landed text carries the feed's time in the airport's zone and the belt",
      landed_text == "Your flight to Bangalore has landed, 11:42 PM IST. Bags on belt 2.", landed_text)
check("landed once, never again", N.LANDED not in kinds(run(steps[5:], ns=ns)[1]))
check("for the person meeting it, the subject is the origin",
      N.render(got[0][1], owned=False) == "The flight from Mumbai has landed, 11:42 PM IST. Bags on belt 2.",
      N.render(got[0][1], owned=False))
check("no sentence sends anyone to the airline", not any("check with" in N.render(m).lower() for _, m in got))
check("no flight number leads a sentence", not any(N.render(m).startswith("6E") for _, m in got))

# ── GATE CHURN, SEVENTEEN HOURS OUT ─────────────────────────────────────────
print("-- seven gate changes in twelve hours, seventeen hours before departure --")
sched = T(21, 30, day=9)
t0 = sched - timedelta(hours=29)
churn = [(t0, dto(gate="12", sched=sched, arr_sched=sched + timedelta(hours=2)), None)]
gates = ["14", "12", "18", "12", "20", "14", "22"]
for i, g in enumerate(gates):
    for k in range(6):  # each gate holds for six 30-minute polls (~3h) — plenty to "settle"
        churn.append((t0 + timedelta(hours=12 * (i + 1) / 7 * 1.0) + timedelta(minutes=30 * k),
                      dto(gate=g, sched=sched, arr_sched=sched + timedelta(hours=2)), None))
ns, got = run(churn)
check("zero messages", got == [], kinds(got))
check("...and the churn left no settle state behind: outside the window a gate is not even tracked",
      ns["notified"]["gate"] == "12" and "gate" not in ns["settle"], ns["settle"].get("gate"))
opened = run([(sched - timedelta(hours=4), dto(gate="22", sched=sched, arr_sched=sched + timedelta(hours=2)), None),
              (sched - timedelta(hours=3, minutes=55), dto(gate="22", sched=sched, arr_sched=sched + timedelta(hours=2)), None)], ns=ns)[1]
check("when the window opens, the current gate becomes the baseline and is not reported as a change", opened == [], kinds(opened))

print("-- gate changes inside four hours --")
sched = T(21, 30, day=9)
base = lambda g, mins: (sched - timedelta(hours=4) + timedelta(minutes=mins), dto(gate=g, sched=sched, arr_sched=sched + timedelta(hours=2)), None)
steps = [base("12", -600), base("12", -300),           # seeded far out with gate 12
         base("12", 0),                                # the window opens: 12 is the baseline
         base("14", 5), base("14", 10),                # 14 held two polls -> message
         base("16", 15), base("14", 20), base("14", 25),  # 16 for one poll then back: nothing
         base("18", 60), base("18", 65),               # 18 held -> message (20-min floor passed)
         base("20", 120), base("20", 125),             # third message
         base("22", 180), base("22", 185),             # fourth change -> cap notice
         base("24", 200), base("24", 205)]             # silence
ns, got = run(steps)
check("three gate messages then the cap notice, then silence",
      kinds(got) == [N.GATE, N.GATE, N.GATE, N.GATE_CAP], kinds(got))
check("the first names the old gate", N.render(got[0][1]) == "Your flight to Bangalore has moved to gate 14, was 12.", N.render(got[0][1]))
check("the flip to 16 and back was invisible", not any(m["values"].get("gate") == "16" for _, m in got))
check("the cap text", N.render(got[3][1]) == "Your flight to Bangalore's gate keeps changing. Terminal will show the current one when you open it.")
first_gate = run([base(None, -600), base(None, -300), base(None, 0), base("14", 5), base("14", 10)])[1]
check("a first assignment inside the window is told with the terminal",
      bool(first_gate) and N.render(first_gate[0][1]) == "Your flight to Bangalore departs from gate 14, Terminal 2.", N.render(first_gate[0][1]) if first_gate else None)

print("-- a gate that reverts after it was told --")
steps = [base("12", -600), base("12", -300), base("12", 0), base("14", 5), base("14", 10), base("12", 35), base("12", 40)]
got = run(steps)[1]
check("the revert is its own message", kinds(got) == [N.GATE, N.GATE] and got[1][1]["values"] == {"gate": "12", "was": "14", "terminal": "2"}, kinds(got))

# ── TERMINAL ────────────────────────────────────────────────────────────────
print("-- terminal --")
steps = [(sched - timedelta(days=3), dto(term="2", sched=sched), None),
         (sched - timedelta(days=2), dto(term="1", sched=sched), None), (sched - timedelta(days=2, hours=-1), dto(term="1", sched=sched), None),
         (sched - timedelta(hours=20), dto(term="1", sched=sched), None), (sched - timedelta(hours=19), dto(term="1", sched=sched), None)]
got = run(steps)[1]
check("a terminal change two days out waits for the 24-hour window", kinds(got) == [N.TERMINAL] and got[0][0] == sched - timedelta(hours=19), [(t, m["kind"]) for t, m in got])
check("terminal text", N.render(got[0][1]) == "Your flight to Bangalore now departs from Terminal 1, not Terminal 2.", N.render(got[0][1]))

# ── DELAY ───────────────────────────────────────────────────────────────────
print("-- delay bands --")
def dl(mins_before, est_delay):
    now = sched - timedelta(minutes=mins_before)
    return (now, dto(est=sched + timedelta(minutes=est_delay) if est_delay else None, sched=sched), None)
steps = [dl(700, 0), dl(690, 0),                       # seed and inside 12h
         dl(600, 40), dl(595, 40),                     # first delay notice
         dl(590, 43), dl(585, 43),                     # +3: swallowed
         dl(580, 60), dl(575, 60),                     # +20 but inside the 30-min floor: wait
         dl(560, 60), dl(555, 60),                     # now past the floor -> further
         dl(500, 15), dl(495, 15),                     # shortened by 45 -> notice
         dl(450, 3), dl(445, 3)]                       # back on schedule
got = run(steps)[1]
check("first, further, shorter, on time", kinds(got) == [N.DELAY, N.DELAY, N.DELAY, N.ON_TIME], kinds(got))
texts = [N.render(m) for _, m in got]
check("first delay text", texts[0] == "Your flight to Bangalore is delayed 40 min. Now expected 10:10 PM IST from Mumbai.", texts[0])
check("further text", texts[1] == "Your flight to Bangalore is delayed further, now 1 h. Expected 10:30 PM IST.", texts[1])
check("shorter text", texts[2] == "Your flight to Bangalore's delay has shortened to 15 min. Expected 9:45 PM IST.", texts[2])
check("on-time text", texts[3] == "Your flight to Bangalore is back on schedule, 9:30 PM IST from Mumbai.", texts[3])
far = run([(sched - timedelta(hours=30), dto(sched=sched), None), (sched - timedelta(hours=20), dto(est=sched + timedelta(hours=2), sched=sched), None),
           (sched - timedelta(hours=19), dto(est=sched + timedelta(hours=2), sched=sched), None)])[1]
check("a two-hour delay twenty hours out is swallowed", far == [], kinds(far))

# ── AFTER DEPARTURE ─────────────────────────────────────────────────────────
print("-- after departure --")
act = sched + timedelta(minutes=5)
steps = [(sched - timedelta(hours=1), dto(sched=sched), None),
         (act + timedelta(minutes=2), dto("active", act=act, arr_est=sched + timedelta(hours=2), sched=sched, arr_sched=sched + timedelta(hours=2)), None),
         (act + timedelta(minutes=7), dto("active", act=act, arr_est=sched + timedelta(hours=2), sched=sched, arr_sched=sched + timedelta(hours=2)), None),
         (act + timedelta(minutes=20), dto("active", act=act, arr_est=sched + timedelta(hours=2, minutes=8), sched=sched, arr_sched=sched + timedelta(hours=2)), None),
         (act + timedelta(minutes=50), dto("active", act=act, arr_est=sched + timedelta(hours=2, minutes=25), sched=sched, arr_sched=sched + timedelta(hours=2)), None)]
got = run(steps)[1]
check("departed, then one arrival move of 25 minutes; the 8-minute one swallowed", kinds(got) == [N.DEPARTED, N.ARRIVAL_MOVED], kinds(got))
check("arrival text", N.render(got[1][1]) == "Your flight to Bangalore is now due around 11:55 PM IST, 25 min later.", N.render(got[1][1]))
check("meeting-side subject", N.render(got[1][1], owned=False).startswith("The flight from Mumbai is now due"))

# ── LANDED WITHOUT A BELT, THEN THE BELT ────────────────────────────────────
print("-- belt after landing --")
L = {"outcome": "landed", "landed_utc": (act + timedelta(hours=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "diverted_to": None}
land_at = act + timedelta(hours=2)
steps = [(sched - timedelta(hours=1), dto(sched=sched), None),
         (land_at + timedelta(minutes=2), dto("active", act=act, sched=sched), L),
         (land_at + timedelta(minutes=10), dto("landed", act=act, sched=sched, belt="5"), L),
         (land_at + timedelta(minutes=12), dto("landed", act=act, sched=sched, belt="5"), L),
         (land_at + timedelta(minutes=30), dto("landed", act=act, sched=sched, belt="7"), L),
         (land_at + timedelta(minutes=32), dto("landed", act=act, sched=sched, belt="7"), L),
         (land_at + timedelta(minutes=50), dto("landed", act=act, sched=sched, belt="9"), L),
         (land_at + timedelta(minutes=52), dto("landed", act=act, sched=sched, belt="9"), L)]
got = run(steps)[1]
check("landed without a belt, then the belt, then one change, then the cap", kinds(got) == [N.LANDED, N.BELT, N.BELT], kinds(got))
check("landed text without belt", N.render(got[0][1]).endswith("has landed, 11:35 PM IST."), N.render(got[0][1]))
check("belt text", N.render(got[1][1]) == "Your flight to Bangalore: bags on belt 5.", N.render(got[1][1]))
late = run([(sched - timedelta(hours=1), dto(sched=sched), None), (land_at + timedelta(minutes=2), dto("active", act=act, sched=sched), L),
            (land_at + timedelta(hours=2), dto("landed", act=act, sched=sched, belt="5"), L), (land_at + timedelta(hours=2, minutes=2), dto("landed", act=act, sched=sched, belt="5"), L)])[1]
check("a belt two hours after landing is not worth a buzz", kinds(late) == [N.LANDED], kinds(late))
elsewhere = run([(sched - timedelta(hours=1), dto(sched=sched), None),
                 (land_at, dto("diverted", act=act, sched=sched), dict(L, diverted_to="VOHS"))])[1]
check("a diversion says so and a landing elsewhere says so",
      kinds(elsewhere) == [N.DIVERTED, N.LANDED] and "though not at Bangalore" in N.render(elsewhere[1][1]), [N.render(m) for _, m in elsewhere])
check("diversion text", N.render(elsewhere[0][1]) == "Your flight to Bangalore has been diverted. Terminal does not yet know where it landed, and will say when it does.")

# ── CANCELLATION AND THE NEXT FLIGHT ────────────────────────────────────────
print("-- cancellation --")
def board(schedule):
    """schedule: {day: [(flight, airline, HH:MM, status)]}. Counts calls."""
    calls = []
    def lookup(o, d, day):
        calls.append(day)
        rows = []
        for num, al, hhmm, st in schedule.get(day, []):
            h, m = map(int, hhmm.split(":"))
            t = datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=IST)
            rows.append({"flight_number": num, "airline": al, "status": st,
                         "departure_scheduled": clock(t), "departure_scheduled_iso": iso(t)})
        return rows
    lookup.calls = calls
    return lookup

sched = T(21, 30, day=9)
lk = board({"2026-09-09": [("6E6188", "IndiGo", "21:30", "cancelled"), ("AI2812", "Air India", "20:00", "scheduled"), ("6E5294", "IndiGo", "23:55", "scheduled")]})
got = run([(sched - timedelta(hours=6), dto(sched=sched), None), (sched - timedelta(hours=5), dto("cancelled", sched=sched), None)], lookup=lk)[1]
# ── AND THE EARLIER ONE IS THE ANSWER, WHICH IS A REVERSAL ──────────────────
# This assertion used to read "skipping the earlier", and the 20:00 was skipped
# because the filter was anchored to the cancelled flight\'s own 21:30. Told at
# 16:30, a passenger can make the 20:00 and would rather: the only floor that
# means anything is whether they can still get there, which is NEXT_MIN_LEAD.
check("the earliest reachable departure wins, even one leaving before the cancelled flight would have",
      kinds(got) == [N.CANCELLED] and got[0][1]["values"]["next"]["flight_number"] == "AI2812", got[0][1]["values"] if got else None)
check("cancellation text", N.render(got[0][1]) == "Your flight to Bangalore is cancelled. The next one leaves today at 8:00 PM IST, Air India AI2812.", N.render(got[0][1]))
# ── BOTH EDGES OF THAT FLOOR, because a rule with only one test passes just as
# happily when it is inverted. Ninety minutes is the line: a departure inside it
# is unreachable and must not be offered, one outside it must.
near = board({"2026-09-09": [("6E1111", "IndiGo", "17:45", "scheduled"), ("6E2222", "IndiGo", "18:30", "scheduled")]})
edge = run([(sched - timedelta(hours=6), dto(sched=sched), None),
            (T(16, 30, day=9), dto("cancelled", sched=sched), None)], lookup=near)[1]
check("a departure inside the ninety minutes is not offered; the one past it is",
      edge[0][1]["values"]["next"]["flight_number"] == "6E2222", edge[0][1]["values"]["next"])
# ── AND THE BOARD IS KEPT, NOT THROWN AWAY ──────────────────────────────────
rows = run([(sched - timedelta(hours=6), dto(sched=sched), None),
            (sched - timedelta(hours=5), dto("cancelled", sched=sched), None)], lookup=board(
    {"2026-09-09": [("AI2812", "Air India", "20:00", "scheduled"),
                    ("6E5294", "IndiGo", "23:55", "scheduled"),
                    ("6E6188", "IndiGo", "21:30", "cancelled")]}))[0]["next_search"]
check("every qualifying row is kept, in time order, cancelled ones excluded",
      [r["flight_number"] for r in rows["rows"]] == ["AI2812", "6E5294"], rows.get("rows"))
check("and the search is dated, so the drawer can say how old it is", rows["searched_at"] is not None)
check("one day of board asked", lk.calls == ["2026-09-09"], lk.calls)
check("a tap opens the route list, earliest first", N.deep_link(got[0][1]) == {"screen": "search", "from": "BOM", "to": "BLR", "date": "2026-09-09", "sort": "earliest"}, N.deep_link(got[0][1]))
check("not deferred: departure is inside a day", got[0][1]["deliver_after"] is None)

lk = board({"2026-09-13": [("AI2812", "Air India", "06:05", "scheduled")]})
c0 = sched - timedelta(days=1)
steps = [(c0 - timedelta(hours=1), dto(sched=sched), None), (c0, dto("cancelled", sched=sched), None),
         (c0 + timedelta(minutes=30), dto("cancelled", sched=sched), None), (c0 + timedelta(hours=1), dto("cancelled", sched=sched), None)]
ns, got = run(steps, lookup=lk)
check("nothing for three days: cancelled now, next flight when found two polls later",
      kinds(got) == [N.CANCELLED, N.NEXT_FLIGHT], kinds(got))
check("the first message admits the search honestly", N.render(got[0][1]) == "Your flight to Bangalore is cancelled. Terminal is looking for the next departure and will tell you.", N.render(got[0][1]))
check("the follow-up names the day", N.render(got[1][1]) == "The next flight to Bangalore leaves Sunday at 6:05 AM IST, Air India AI2812.", N.render(got[1][1]))
check("three days in the first pass, then two per poll: 09,10,11 | 12,13", lk.calls == ["2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"], lk.calls)
check("the search is closed", ns["next_search"]["done"] is True)
more = run([(c0 + timedelta(hours=2), dto("cancelled", sched=sched), None)], ns=ns, lookup=lk)[1]
check("and asks nothing more", more == [] and len(lk.calls) == 5)

lk = board({})
steps = [(c0 - timedelta(hours=1), dto(sched=sched), None), (c0, dto("cancelled", sched=sched), None)]
steps += [(c0 + timedelta(minutes=30 * i), dto("cancelled", sched=sched), None) for i in range(1, 40)]
ns, got = run(steps, lookup=lk)
# SEVEN BOARDS, NOT SIXTY. The ceiling is what a stranded passenger will read
# rather than how far the timetable is published; see NEXT_MAX_DAYS. At four
# units a board this is the difference between 28 units and 240 for one
# cancellation on a route with no service.
check("an empty route stops at a week and says so once", kinds(got) == [N.CANCELLED, N.NEXT_FLIGHT] and len(lk.calls) == 7, (kinds(got), len(lk.calls)))
check("the exhausted text says what it looked at, not that the schedule ends",
      N.render(got[1][1]) == "Nothing else to Bangalore on this route in the next week.", N.render(got[1][1]))
check("and the cancelled branch says the same thing about itself",
      N.render(dict(got[0][1], values={"none_within_days": N.NEXT_MAX_DAYS}))
      == "Your flight to Bangalore is cancelled. Nothing else on this route in the next week.",
      N.render(dict(got[0][1], values={"none_within_days": N.NEXT_MAX_DAYS})))

withdrawn = run([(sched - timedelta(hours=6), dto(sched=sched), None), (sched - timedelta(hours=5), dto("cancelled", sched=sched), None),
                 (sched - timedelta(hours=4), dto("scheduled", sched=sched), None)], lookup=board({}))[1]
check("a cancellation withdrawn is said, not swallowed", kinds(withdrawn) == [N.CANCELLED, N.CANCEL_WITHDRAWN])
check("withdrawn text", N.render(withdrawn[1][1]) == "Your flight to Bangalore is no longer showing as cancelled. Scheduled 9:30 PM IST from Mumbai.", N.render(withdrawn[1][1]))

print("-- the night --")
far_sched = T(21, 30, day=12)
night = T(2, 15, day=9)
got = run([(night - timedelta(hours=1), dto(sched=far_sched), None), (night, dto("cancelled", sched=far_sched), None)], lookup=board({}))[1]
check("a 2 AM cancellation three days out is deferred to 7 AM at the airport",
      got[0][1]["deliver_after"] == N._iso(T(7, 0, day=9).astimezone(timezone.utc)), got[0][1]["deliver_after"])
got = run([(night - timedelta(hours=1), dto(sched=T(9, 0, day=9)), None), (night, dto("cancelled", sched=T(9, 0, day=9)), None)], lookup=board({}))[1]
check("a 2 AM cancellation of a 9 AM flight is not deferred", got[0][1]["deliver_after"] is None)

# ── THE SUBJECT LADDER ──────────────────────────────────────────────────────
print("-- the subject --")
m = got[0][1]
check("one flight to the city", N.subject(m) == "Your flight to Bangalore")
check("two to the same city that day: the time joins", N.subject(m, same_city=2) == "Your 9:00 AM flight to Bangalore", N.subject(m, same_city=2))
check("same city and same time: the airline joins", N.subject(m, same_city=2, same_time=2) == "Your 9:00 AM IndiGo flight to Bangalore")
check("meeting it: the origin leads", N.subject(m, owned=False, same_city=2) == "The 9:00 AM flight from Mumbai")
check("owned unknown reads as on it", N.subject(m, owned=None) == "Your flight to Bangalore")

# ── NOT TWICE ───────────────────────────────────────────────────────────────
print("-- not twice --")
steps = [base("12", -600), base("12", -300), base("12", 0), base("14", 5), base("14", 10)]
ns, got = run(steps)
again = run([base("14", 15), base("14", 20)], ns=ns)[1]
check("the same gate is never told twice", got and again == [])
check("the outbox holds the message with its key, and the key is remembered",
      len(ns["outbox"]) == 1 and ns["outbox"][0]["key"] in ns["keys"])
check("the outbox is bounded", N.OUTBOX_MAX == 40)

print()
print("-- a delay that threatens the connection --")


def onward(dep=T(0, 40, day=8), origin="BLR", dep_country="IN", arr_country="IN",
           number="6E777", city="Bangalore"):
    """The leg the 6E6188 dto above connects INTO: BLR onward."""
    return {
        "flight_number": number, "flight_date": "2026-09-08", "airline": "IndiGo",
        "status": "scheduled",
        "departure": {"airport": "Bangalore Bengaluru", "city": city, "iata": origin,
                      "country": dep_country, "timezone": "Asia/Kolkata",
                      "scheduled": clock(dep), "scheduled_iso": iso(dep)},
        "arrival": {"airport": "Delhi", "city": "Delhi", "iata": "DEL",
                    "country": arr_country, "timezone": "Asia/Kolkata",
                    "scheduled": clock(T(3, 30, day=8)), "scheduled_iso": iso(T(3, 30, day=8))},
    }


def home(dep_country="IN", arr_country="IN", **kw):
    """The 6E6188 dto with countries on both ends."""
    d = dto(**kw)
    d["departure"]["country"] = dep_country
    d["arrival"]["country"] = arr_country
    return d


# THE ARITHMETIC, AT EACH BOUNDARY. Arrival 23:25, so a 00:40 departure is
# 75 minutes: inside the domestic minimum plus the cushion, and not below it.
band = lambda d, n: (N.connection_band(d, n) or (None,))[0]
check("comfortable well clear of the minimum",
      band(home(), onward(dep=T(2, 0, day=8))) == "comfortable")
check("at risk inside the cushion",
      band(home(), onward(dep=T(0, 40, day=8))) == "at_risk")
check("at risk exactly at the minimum",
      band(home(), onward(dep=T(0, 25, day=8))) == "at_risk")
check("at risk exactly at the top of the cushion",
      band(home(), onward(dep=T(0, 55, day=8))) == "at_risk")
check("comfortable one minute above it",
      band(home(), onward(dep=T(0, 56, day=8))) == "comfortable")
check("will miss below the minimum",
      band(home(), onward(dep=T(0, 20, day=8))) == "will_miss")

# THE DELAY IS WHAT MOVES IT. One timetable -- a 23:25 arrival into a 02:00
# departure, two and a half hours clear -- read at three different arrivals.
check("the timetable alone is comfortable",
      band(home(), onward(dep=T(2, 0, day=8))) == "comfortable")
check("a delayed arrival turns that comfortable connection tight",
      band(home(arr_est=T(0, 45, day=8)), onward(dep=T(2, 0, day=8))) == "at_risk")
check("and a worse one turns it into a miss",
      band(home(arr_est=T(1, 30, day=8)), onward(dep=T(2, 0, day=8))) == "will_miss")
check("an ACTUAL arrival outranks the estimate",
      band(home(arr_est=T(1, 30, day=8), arr_act=T(23, 30)),
           onward(dep=T(2, 0, day=8))) == "comfortable")

# THE BORDER RAISES THE MINIMUM, and an unknown country counts as one.
check("the same 75 minutes is a miss when a leg crosses a border",
      band(home(), onward(dep=T(0, 40, day=8), arr_country="AE")) == "will_miss")
# A DTO STORED BEFORE _build_movement CARRIED THE COUNTRY HAS NONE, and the
# shorter minimum must not be what it falls back to.
check("a country nobody recorded is treated as a crossing",
      band(home(dep_country=None), onward(dep=T(0, 40, day=8))) == "will_miss")
# THE HUB IS NAMED BY BOTH LEGS, so one side recording it is enough.
check("the hub's country is taken from whichever leg has it",
      band(home(arr_country=None), onward(dep=T(0, 40, day=8))) == "at_risk")

check("no connection when the airports do not meet",
      N.connection_band(home(), onward(origin="MAA")) is None)
check("no connection when the gap is wider than a day",
      N.connection_band(home(), onward(dep=T(23, 40, day=8))) is None)

# ── WOULD A REPLACEMENT STILL MAKE THE CONNECTION ───────────────────────────
#
# The same hub and the same minimum, asked of a BOARD ROW rather than of the
# leg the passenger is on. Onward leaves BLR at 00:40, so domestic 60 + 30 of
# cushion puts at_risk in (60, 90] minutes and a miss under 60.
print()
print("-- replacements against the next leg --")


def row(arr=None, num="6E100", dest="BLR"):
    return {"flight_number": num, "airline": "IndiGo", "destination_iata": dest,
            "departure_scheduled_iso": iso(T(19, 0)),
            "arrival_scheduled_iso": iso(arr) if arr else None}


def verdicts(rows, nxt=onward()):
    return [(r["connects"], r["layover_minutes"])
            for r in N.classify_alternatives(home(), nxt, rows)]

check("lands well clear: comfortable, with the layover in minutes",
      verdicts([row(T(22, 0))]) == [("comfortable", 160)], verdicts([row(T(22, 0))]))
check("lands inside the cushion: at risk",
      verdicts([row(T(23, 25))]) == [("at_risk", 75)], verdicts([row(T(23, 25))]))
check("lands too late: will miss",
      verdicts([row(T(0, 10, day=8))]) == [("will_miss", 30)], verdicts([row(T(0, 10, day=8))]))

# ── AND THE ROW WITH NO ARRIVAL TIME, WHICH IS THE WHOLE POINT ──────────────
# A board row can name a destination and carry no arrival time at all. Calling
# that a miss would hide a usable flight behind a number nobody had; calling it
# comfortable would promise a connection on no evidence.
check("no arrival time is unknown, and is neither a miss nor a promise",
      verdicts([row(None)]) == [("unknown", None)], verdicts([row(None)]))
check("and it is not dropped: every row that went in comes out",
      len(N.classify_alternatives(home(), onward(), [row(T(22, 0)), row(None), row(T(0, 10, day=8))])) == 3)

check("no next leg at all: every row is simply a flight to the destination",
      verdicts([row(T(22, 0))], nxt=None) == [(None, None)], verdicts([row(T(22, 0))], nxt=None))
check("a row that does not go to the hub cannot have a layover",
      verdicts([row(T(22, 0), dest="MAA")]) == [(None, None)], verdicts([row(T(22, 0), dest="MAA")]))

# THE MINIMUM TRAVELS WITH THE ROW, so the drawer can say what it was judged
# against, and an international hub raises it for a replacement exactly as it
# does for the leg being flown.
dom = N.classify_alternatives(home(), onward(), [row(T(22, 0))])[0]
intl = N.classify_alternatives(home(arr_country="AE"), onward(), [row(T(22, 0))])[0]
check("the domestic minimum is reported", dom["minimum_minutes"] == 60, dom["minimum_minutes"])
check("crossing a border raises it for a replacement too, and 160 minutes still clears it",
      (intl["minimum_minutes"], intl["connects"]) == (120, "comfortable"), intl)

# ── THE BLOCK THE DEVICE READS ──────────────────────────────────────────────
blk = N.alternatives_block(home(), onward(),
                           {"rows": [row(T(22, 0)), row(None)], "searched_at": "2026-09-07T18:00:00+00:00",
                            "days_searched": 1, "done": True}, T(18, 0))
check("the block names the route it searched", (blk["origin"], blk["destination"]) == ("BOM", "BLR"), blk["origin"])
check("it carries the age of the search", blk["searched_at"] == "2026-09-07T18:00:00+00:00")
check("and how far it looked", (blk["days_searched"], blk["max_days"], blk["done"]) == (1, N.NEXT_MAX_DAYS, True))
check("it summarises the leg the connection is for, without embedding the whole DTO",
      blk["next_leg"]["flight_number"] == "6E777" and "arrival" not in blk["next_leg"], blk["next_leg"])
check("both rows survive into it, verdicts and all",
      [r["connects"] for r in blk["rows"]] == ["comfortable", "unknown"], blk["rows"])
check("a final leg has no next_leg block at all",
      N.alternatives_block(home(), None, {"rows": [row(T(22, 0))]}, T(18, 0))["next_leg"] is None)

# ── THE MESSAGES ──
NOW = T(20, 0)


def run(d, n, prior=None, now=NOW):
    return N.decide(prior or seeded(d), d, None, now, connection=n)


def seeded(d):
    ns, _ = N.decide(N.blank_notify_state(), d, None, T(19, 0))
    return ns


ns, out = run(home(arr_est=T(0, 45, day=8)), onward(dep=T(2, 0, day=8)))
check("one message when the band worsens", [m["kind"] for m in out] == [N.CONNECTION], out)
check("it names the onward flight and what is left",
      "6E777" in N.render(out[0]) and "1 h 15 min" in N.render(out[0]), N.render(out[0]))
# THE SUBJECT ALREADY PLACED THE READER. "your flight to Bangalore ... in
# Bangalore" is what this wording exists to avoid; see render.
check("connection text, with the hub said once",
      N.render(out[0]) == "Your flight to Bangalore is running late enough to put 6E777"
                          " at risk -- about 1 h 15 min between them,"
                          " where 1 h is the usual minimum.",
      N.render(out[0]))
# AND IT IS KEPT WHERE THE SUBJECT COULD NOT SAY IT. A leg whose arrival city
# never reached the DTO gets a subject with no place in it, and then this
# clause is the only thing telling the reader where they will be.
placeless = copy.deepcopy(out[0])
placeless["destination"] = {"iata": "BLR", "city": None}
check("and the hub IS named when the subject could not name it",
      " in Bangalore" in N.render(placeless), N.render(placeless))
check("a tap opens the flight at risk, not the delayed one",
      N.deep_link(out[0]) == {"screen": "flight", "flight_number": "6E777", "date": "2026-09-08"},
      N.deep_link(out[0]))

ns2, out2 = run(home(arr_est=T(0, 45, day=8)), onward(dep=T(2, 0, day=8)), prior=ns)
check("the same band again says nothing", out2 == [], out2)

ns3, out3 = run(home(arr_est=T(1, 30, day=8)), onward(dep=T(2, 0, day=8)), prior=ns)
check("a worse band speaks once more", [m["kind"] for m in out3] == [N.CONNECTION], out3)
check("miss text",
      N.render(out3[0]).startswith("Your flight to Bangalore is running late enough to miss 6E777"),
      N.render(out3[0]))
check("and it does not send them to the airline",
      "check with" not in N.render(out3[0]).lower(), N.render(out3[0]))

_, out4 = run(home(), onward(dep=T(2, 0, day=8)), prior=ns3)
check("an IMPROVING connection is never reported", out4 == [], out4)

# SEEDED ON A HEALTHY LEG, then handed the disrupted one: seeding on the
# cancelled dto itself would record the status as already known and emit
# nothing at all, which tests only the seeder.
healthy = seeded(home())
_, out5 = run(home(status="cancelled", arr_est=T(1, 30, day=8)), onward(dep=T(2, 0, day=8)),
              prior=healthy)
check("a cancelled leg says cancelled and not connection",
      [m["kind"] for m in out5] == [N.CANCELLED], out5)

_, out6 = run(home(status="diverted", arr_est=T(1, 30, day=8)), onward(dep=T(2, 0, day=8)),
              prior=healthy)
check("a diverted leg says diverted and not connection",
      [m["kind"] for m in out6] == [N.DIVERTED], out6)

_, out7 = run(home(arr_est=T(1, 30, day=8)), None)
check("no next leg, no connection message",
      not any(m["kind"] == N.CONNECTION for m in out7), out7)

# ── THE RULE, OVER EVERY KIND THIS FILE PRODUCES ────────────────────────────
#
# THERE WAS ALREADY A CHECK FOR THIS and it was scoped to the 6E6188 replay --
# which is exactly how "Check with the airline" reached the connection message
# and survived a review: the guard was real, and it was not looking here.
# Scoped to every message any test in this file has built instead.
print()
print("-- and nothing anywhere sends the reader to the airline --")
everything = [m for _, m in got] + out + out2 + out3 + out4 + out5 + out6 + out7
sent = [N.render(m) for m in everything
        if "check with" in N.render(m).lower() or "contact the airline" in N.render(m).lower()]
check("NO message of any kind sends anyone to the airline", sent == [], sent)
# AND THE SET IS NOT EMPTY OF THE ONE THAT BROKE IT. A guard over a list that
# happens to hold nothing passes for the wrong reason; naming the kind is what
# makes this a test of the connection message rather than of the loop.
kinds_seen = {m["kind"] for m in everything}
check("and the set includes the kind that broke the rule",
      N.CONNECTION in kinds_seen and len(kinds_seen) >= 4, sorted(kinds_seen))

print("\nPASSED: %d   FAILURES: %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
