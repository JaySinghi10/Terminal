"""The /intent endpoint, offline.

    python test_intent.py

FOUR QUESTIONS.

FIRST: is an intent RETURNED and never RUN? search_route must not touch a
provider here -- the device runs it. Both providers are replaced with functions
that raise.

SECOND: is nothing the model says trusted? Dates re-bounded, enums re-tested,
flight numbers normalised and refused when they are not one.

THIRD: is prose the answer, with no second call? The forced retry was measured
by tools/eval_intent.py and retired; see the note above /intent in api.py.

FOURTH: never blank. Every path returns an intent, prose, or a named error.

The model is a queue of canned turns; each test says what the next turn is.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api                                           # noqa: E402
import llm                                           # noqa: E402

FAILURES = []
PASS = 0


def check(name, ok, detail=""):
    global PASS
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "   -> %r" % (detail,)))
    if ok:
        PASS += 1
    else:
        FAILURES.append(name)


# ── THE FAKE MODEL ───────────────────────────────────────────────────────────
QUEUE = []
CALLS = []


def fake_generate(**kw):
    CALLS.append(kw)
    if not QUEUE:
        raise AssertionError("the model was asked more times than the test allowed")
    nxt = QUEUE.pop(0)
    if isinstance(nxt, Exception):
        raise nxt
    return nxt


def call(name, **args):
    return llm.ToolCall(name=name, args=args)


def turn(text="", *calls):
    return llm.Turn(text=text, tool_calls=list(calls), raw={"fake": True})


llm.generate = fake_generate


def _forbidden(*a, **k):
    raise AssertionError("/intent reached a provider")


api.fetch_route = _forbidden
api.fetch_flight_full = _forbidden
api._gmail_access = lambda request, token: (None, None)


class _Req:
    headers = {}


def ask(message, today="2026-09-22", has_place=False, *turns):
    QUEUE[:] = list(turns)
    CALLS.clear()
    return api.intent(api.IntentRequest(message=message, today=today, has_place=has_place), _Req())


print("-- a route intent is returned, not run --")
r = ask("delhi to indore flights", "2026-09-22", False,
        turn("", call("search_route", origin="Delhi", destination="Indore", confidence=0.98)))
check("kind route, names as given", r["intent"] and r["intent"]["kind"] == "route"
      and (r["intent"]["origin"], r["intent"]["destination"]) == ("Delhi", "Indore"), r)
check("no prose, no error, no flight, no retry flag",
      r["response"] is None and r["error"] is None and r["flight"] is None and "retried" not in r, r)
check("one model call, tool choice auto", len(CALLS) == 1 and CALLS[0].get("forced_tool") is None, CALLS)
check("the device's date reached the prompt", "Today is 2026-09-22" in CALLS[0]["system"])
check("the three tools were offered", [t["name"] for t in CALLS[0]["tools"]]
      == ["search_route", "lookup_flight", "find_flight_from_gmail"], [t["name"] for t in CALLS[0]["tools"]])

r = ask("flights to indore", "2026-09-22", False,
        turn("", call("search_route", destination="Indore", confidence=0.9)))
check("an omitted origin stays omitted -- the device decides what to assume", r["intent"]["origin"] is None, r)

print()
print("-- nothing the model says is trusted --")
# TOMORROW BY THE SERVER'S UTC CLOCK, which is what the date is bounded against;
# a fixed date here would expire the day it fell a day into the past.
first_day = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Goa", date=first_day, date_kind="range",
                      range_label="this weekend", band="morning", sort="fastest", confidence=0.9)))
i = r["intent"]
check("a range keeps its FIRST day, its kind and the user's words",
      (i["date"], i["date_kind"], i["range_label"]) == (first_day, "range", "this weekend"), i)
check("band and sort pass when in vocabulary", (i["band"], i["sort"]) == ("morning", "fastest"))

r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Goa", band="dawn", sort="cheapest", date_kind="fortnight", confidence=7)))
i = r["intent"]
check("an out-of-vocabulary band, sort and kind are dropped, not passed through",
      (i["band"], i["sort"], i["date_kind"]) == (None, None, None), i)
check("confidence is clamped to 1", i["confidence"] == 1.0, i["confidence"])

r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Indore", question="next", confidence=0.9)))
check("a question in vocabulary passes", r["intent"]["question"] == "next", r["intent"])
r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Indore", question="cheapest", confidence=0.9)))
check("a question out of vocabulary is dropped", r["intent"]["question"] is None, r["intent"])
r = ask("x", "2026-09-22", False, turn("", call("search_route", destination="Indore", confidence=0.9)))
check("no question is None, not absent", "question" in r["intent"] and r["intent"]["question"] is None, r["intent"])

r = ask("x", "2026-09-22", False,
        turn("", call("search_route", origin="Lima", destination="Santiago", destination_country="Chile", confidence=0.9)))
check("a country hint passes through, and the one not given is None",
      r["intent"]["destination_country"] == "Chile" and r["intent"]["origin_country"] is None, r["intent"])
r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Goa", destination_country="   ", confidence=0.9)))
check("a blank country is None", r["intent"]["destination_country"] is None, r["intent"])

r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Goa", date="2020-01-01", confidence=0.9)))
check("a past date is NOT silently dropped: it is kept as an error for the device to say",
      r["intent"]["date"] is None and r["intent"]["date_error"], r["intent"])
r = ask("x", "2026-09-22", False,
        turn("", call("search_route", destination="Goa", date="not a date", confidence=0.9)))
check("a malformed date the same", r["intent"]["date"] is None and r["intent"]["date_error"], r["intent"])

r = ask("x", "2026-09-22", False, turn("", call("search_route", origin="Delhi", confidence=0.9)))
check("no destination is a sentence back, not an intent and not a blank",
      r["intent"] is None and r["response"] == api.INTENT_NO_DESTINATION, r)

print()
print("-- a flight intent --")
for given, want in [("6E5071", "6E5071"), ("6e 5071", "6E5071"), ("6E-5071", "6E5071"),
                    ("ai 2630", "AI2630"), ("sk936", "SK936"), ("ek 500 ", "EK500")]:
    r = ask("x", "2026-09-22", False, turn("", call("lookup_flight", flight_number=given)))
    check(f"'{given}' -> {want}", r["intent"] and r["intent"]["flight_number"] == want, r["intent"])
r = ask("x", "2026-09-22", False, turn("", call("lookup_flight", flight_number="12345")))
check("a digits-only 'number' is refused with a sentence", r["intent"] is None and r["response"] == api.INTENT_BAD_NUMBER, r)
r = ask("x", "2026-09-22", False, turn("", call("lookup_flight", flight_number="indigo")))
check("a bare airline name is refused too", r["intent"] is None and r["response"] == api.INTENT_BAD_NUMBER, r)
# TOMORROW BY THE SERVER'S UTC CLOCK, which is what the date is bounded against;
# a fixed date here expired the day it fell a day into the past.
tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
r = ask("x", "2026-09-22", False, turn("", call("lookup_flight", flight_number="AI2630", date=tomorrow)))
check("a dated lookup keeps its date", r["intent"]["date"] == tomorrow, r["intent"])
r = ask("x", "2026-09-22", False, turn("", call("lookup_flight", flight_number="AI2630", date="2019-01-01")))
check("a past date on a flight is an error, not a silent today", r["intent"]["date"] is None and r["intent"]["date_error"], r["intent"])

print()
print("-- prose is the answer: the forced retry was measured and retired --")
r = ask("what about delhi", "2026-09-22", True, turn("I am not sure what you mean."))
check("prose + a place on the device -> ONE call, and the prose comes back",
      r["intent"] is None and r["response"] == "I am not sure what you mean." and len(CALLS) == 1, r)
check("nothing was forced", all(c.get("forced_tool") is None for c in CALLS), [c.get("forced_tool") for c in CALLS])
r = ask("hello", "2026-09-22", False, turn("Hello. Type a flight number or a route."))
check("prose with NO place on the device -> the same one call",
      r["intent"] is None and r["response"].startswith("Hello") and len(CALLS) == 1, r)

print()
print("-- the gmail tool still runs here, as /chat ran it --")
api.run_tool = lambda name, args, tok: ("AI2630 departs 10:00", {"flight_number": "AI2630"})
r = ask("is my flight on time", "2026-09-22", False,
        turn("", call("find_flight_from_gmail")),
        turn("AI2630 is on time.\nstatus: scheduled"))
check("the tool ran, the flight was captured, the prose came back",
      r["response"].startswith("AI2630") and r["flight"] == {"flight_number": "AI2630"} and r["intent"] is None, r)
check("two model rounds", len(CALLS) == 2)

print()
print("-- never blank --")
r = ask("", "2026-09-22", False)
check("an empty line is a hint, and costs no model call", r["response"] == api.INTENT_EMPTY and len(CALLS) == 0, r)
r = ask("x", "2026-09-22", False, RuntimeError("boom"))
check("a provider failure is a named error string", r["error"] in (api.CHAT_ERROR_GENERIC, api.CHAT_ERROR_BUSY,
                                                                   api.CHAT_ERROR_CREDIT, api.CHAT_ERROR_CONFIG), r)
r = ask("x", "2026-09-22", False, turn(""))
check("no text and no calls is the generic error, not an empty body", r["error"] == api.CHAT_ERROR_GENERIC, r)
r = ask("x", "2026-09-22", False, *[turn("", call("find_flight_from_gmail")) for _ in range(api.CHAT_MAX_TOOL_ROUNDS)])
check("running out of rounds is named", r["error"] == api.CHAT_ERROR_TOO_MANY_STEPS, r)
r = ask("x", "not-a-date", False, turn("", call("search_route", destination="Goa", confidence=0.9)))
check("a malformed device date falls back to the server's, and the call still works",
      r["intent"] is not None and "Today is 20" in CALLS[0]["system"], CALLS[0]["system"][:60])

print("\nPASSED: %d   FAILURES: %d" % (PASS, len(FAILURES)))
sys.exit(1 if FAILURES else 0)
