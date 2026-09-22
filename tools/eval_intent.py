"""Forty phrasings through /intent, scored. Live, against a URL you give it.

    python tools/eval_intent.py https://intent-eval---flight-tracker-....run.app

WHAT IT MEASURES. For each line: did the model pick the right KIND (route,
flight, chat); for a route, did origin and destination resolve to the right
airports and did the date come out as the right day; for a flight, the right
number. A miss on any of those is a misread. The summary is misreads over
forty, by group, and how often the forced retry fired and whether it helped.

WHAT IT COSTS. One model call per line, two where the retry fires. No
AeroDataBox unit: the endpoint never runs a board, and the Gmail tool has no
token here so it answers "sign in".

has_place IS APPROXIMATED. The device computes it with isKnownPlace over the
bundled dataset; this script cannot, so it uses the set of place words that
appear in these forty lines. That is exactly what the device would say for these
lines, and nothing else is being measured.
"""
import json
import sys
import urllib.request
from datetime import date, timedelta

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://flight-tracker-970706733452.asia-south1.run.app"
TODAY = date.today()


def d(days):
    return (TODAY + timedelta(days=days)).isoformat()


def weekday(name, allow_today=False):
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    target = names.index(name)
    delta = (target - TODAY.weekday()) % 7
    if delta == 0 and not allow_today:
        delta = 7
    return d(delta)


NAME_TO_CODE = {
    "delhi": "DEL", "new delhi": "DEL", "del": "DEL", "indore": "IDR", "idr": "IDR",
    "mumbai": "BOM", "bombay": "BOM", "bom": "BOM", "bengaluru": "BLR", "bangalore": "BLR",
    "blr": "BLR", "chennai": "MAA", "madras": "MAA", "kolkata": "CCU", "calcutta": "CCU",
    "goa": "GOA", "hyderabad": "HYD", "hyd": "HYD", "ahmedabad": "AMD", "kochi": "COK",
    "cochin": "COK", "thiruvananthapuram": "TRV", "trivandrum": "TRV", "dubai": "DXB",
    "london": "LON", "new york": "NYC", "pune": "PNQ", "guwahati": "GAU", "lucknow": "LKO",
    "varanasi": "VNS",
}
PLACE_WORDS = set(NAME_TO_CODE) | {"dehli", "dilli", "hyderbad", "chenai", "kolkatta", "banglore",
                                    "kempegowda", "indira gandhi"}


def code(name):
    if name is None:
        return None
    return NAME_TO_CODE.get(str(name).strip().lower(), "?" + str(name))


def has_place(text):
    t = text.lower()
    return any(w in t for w in PLACE_WORDS)


# (line, expected kind, expected origin, expected destination, expected date, expected number)
R, F, C = "route", "flight", "chat"
CASES = [
    # routes, plain
    ("delhi to indore flights", R, "DEL", "IDR", None, None),
    ("dehli to indore", R, "DEL", "IDR", None, None),
    ("flights from delhi to indore tomorrow", R, "DEL", "IDR", d(1), None),
    ("delhi indore", R, "DEL", "IDR", None, None),
    ("IDR to BOM", R, "IDR", "BOM", None, None),
    ("DEL/IDR", R, "DEL", "IDR", None, None),
    ("del-idr 3/10", R, "DEL", "IDR", f"{TODAY.year}-10-03", None),
    # routes, old and local names, airport names
    ("bombay to bangalore", R, "BOM", "BLR", None, None),
    ("dilli se indore ki flight", R, "DEL", "IDR", None, None),
    ("indore se delhi", R, "IDR", "DEL", None, None),
    ("madras to calcutta friday evening", R, "MAA", "CCU", weekday("friday"), None),
    ("kempegowda to indira gandhi", R, "BLR", "DEL", None, None),
    ("trivandrum to dubai", R, "TRV", "DXB", None, None),
    ("banglore to dehli 25 sep", R, "BLR", "DEL", f"{TODAY.year}-09-25", None),
    ("hyderbad to chenai day after tomorrow", R, "HYD", "MAA", d(2), None),
    ("any flights kolkatta to guwahati tonight", R, "CCU", "GAU", d(0), None),
    ("pune goa sunday morning", R, "PNQ", "GOA", weekday("sunday"), None),
    ("fastest way from ahmedabad to kochi on the 24th", R, "AMD", "COK", None, None),
    ("early morning flights blr to hyd", R, "BLR", "HYD", None, None),
    ("flights from london to new york", R, "LON", "NYC", None, None),
    # routes with no origin
    ("flights to indore", R, None, "IDR", None, None),
    ("when is the next flight to indore", R, None, "IDR", None, None),
    ("flights lucknow", R, None, "LKO", None, None),
    # ranges: first day, and the label
    ("show me flights between mumbai and goa this weekend", R, "BOM", "GOA", weekday("saturday", True), None),
    ("cheapest flight delhi to mumbai next week", R, "DEL", "BOM", weekday("monday"), None),
    # flights
    ("6E5071", F, None, None, None, "6E5071"),
    ("is 6E5071 on time", F, None, None, None, "6E5071"),
    ("6e 5071 status", F, None, None, None, "6E5071"),
    ("indigo 5071", F, None, None, None, "6E5071"),
    ("when does SK936 land", F, None, None, None, "SK936"),
    ("AI 2630 tomorrow", F, None, None, d(1), "AI2630"),
    ("track ai2630", F, None, None, None, "AI2630"),
    ("QP1133 on 26 september", F, None, None, f"{TODAY.year}-09-26", "QP1133"),
    ("what gate is ek500", F, None, None, None, "EK500"),
    # chat
    ("is my flight on time", C, None, None, None, None),
    ("what time does my flight land", C, None, None, None, None),
    ("how do I get to the airport", C, None, None, None, None),
    ("cancel my booking", C, None, None, None, None),
    ("hello", C, None, None, None, None),
    ("what is the weather in delhi", C, None, None, None, None),
]
assert len(CASES) == 40, len(CASES)


def post(line):
    body = json.dumps({"message": line, "today": TODAY.isoformat(), "has_place": has_place(line)}).encode()
    req = urllib.request.Request(BASE + "/intent", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def judge(case, reply):
    line, kind, o, dst, day, num = case
    intent = reply.get("intent")
    got_kind = intent["kind"] if intent else ("chat" if reply.get("response") else "error")
    notes = []
    if got_kind != kind:
        notes.append(f"kind {got_kind}")
    if kind == R and intent:
        if code(intent.get("origin")) != o:
            notes.append(f"origin {intent.get('origin')!r}")
        if code(intent.get("destination")) != dst:
            notes.append(f"dest {intent.get('destination')!r}")
        if day is not None and intent.get("date") != day:
            notes.append(f"date {intent.get('date')} not {day}")
    if kind == F and intent:
        if intent.get("flight_number") != num:
            notes.append(f"number {intent.get('flight_number')}")
        if day is not None and intent.get("date") != day:
            notes.append(f"date {intent.get('date')} not {day}")
    return notes


totals = {R: [0, 0], F: [0, 0], C: [0, 0]}
retries = [0, 0]   # fired, helped (kind right after a retry)
rows = []
for case in CASES:
    try:
        reply = post(case[0])
    except Exception as exc:  # noqa: BLE001
        reply = {"error": f"transport: {exc}"}
    notes = judge(case, reply)
    totals[case[1]][1] += 1
    if not notes:
        totals[case[1]][0] += 1
    if reply.get("retried"):
        retries[0] += 1
        if not notes:
            retries[1] += 1
    intent = reply.get("intent")
    shown = (f"{intent['kind']}: {intent.get('origin')}->{intent.get('destination')} {intent.get('date') or ''} {intent.get('range_label') or ''}".strip()
             if intent and intent["kind"] == "route" else
             f"flight: {intent.get('flight_number')} {intent.get('date') or ''}".strip() if intent else
             f"chat: {(reply.get('response') or reply.get('error') or '')[:60]!r}")
    flag = "  ok  " if not notes else "  MISS"
    rows.append(f"{flag} {case[0]:<52} {shown}" + (f"   <- {'; '.join(notes)}" if notes else "")
                + ("  [retried]" if reply.get("retried") else ""))

print("\n".join(rows))
print()
right = sum(v[0] for v in totals.values())
print(f"routes  {totals[R][0]}/{totals[R][1]}   flights {totals[F][0]}/{totals[F][1]}   chat {totals[C][0]}/{totals[C][1]}")
print(f"MISREAD RATE: {40 - right}/40 = {(40 - right) / 40:.1%}")
print(f"forced retry fired {retries[0]} times, and the result was right {retries[1]} of those")
