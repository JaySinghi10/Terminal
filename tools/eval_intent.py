"""Forty phrasings through /intent, scored. Live, against a URL you give it.

    python tools/eval_intent.py https://intent-eval---flight-tracker-....run.app
    python tools/eval_intent.py https://... --set world

THE WORLD SET is a second forty, phrased the way a local would type them:
Spanish, French, German, Italian, Portuguese, Polish, Russian and Turkish for
Europe and the Americas, Arabic and Persian for the Middle East, Japanese,
Chinese and Korean for East Asia, Thai and Indonesian for Southeast Asia, and
the English a local types in Africa, with codes, nicknames and native
separators throughout. Scored like the first forty, plus the country hint on
the two lines that imply one. The question lines are not run with it.

WHAT IT MEASURES. For each line: did the model pick the right KIND (route,
flight, chat); for a route, did origin and destination resolve to the right
airports and did the date come out as the right day; for a flight, the right
number -- and, for a route, whether the model called it a question when it was
one and only then. A miss on any of those is a misread. The summary is misreads
over forty, by group.

THE QUESTION SHAPES ARE SCORED SEPARATELY, after the forty: ten lines over the
seven shapes the line above the board can answer, plus one that must not be read
as a question. Their own count, so the forty stay comparable run to run.

WHAT IT COSTS. One model call per line. No
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

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
WORLD = "--set" in sys.argv and sys.argv[sys.argv.index("--set") + 1:][:1] == ["world"]
BASE = ARGS[0].rstrip("/") if ARGS else "https://flight-tracker-z2b3mixjea-el.a.run.app"
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
    # THE WORLD SET'S NAMES, as the model returns them in English. A metro is a
    # pseudo-code (PAR, TYO) because the device offers its group, not one code.
    "madrid": "MAD", "barcelona": "BCN", "paris": "PAR", "nice": "NCE", "munich": "MUC",
    "berlin": "BER", "rome": "ROM", "milan": "MIL", "warsaw": "WAW", "krakow": "KRK",
    "kraków": "KRK", "moscow": "MOW", "st petersburg": "LED", "st. petersburg": "LED",
    "saint petersburg": "LED", "istanbul": "IST", "ankara": "ESB", "lisbon": "LIS",
    "porto": "OPO", "los angeles": "LAX", "lax": "LAX", "jfk": "JFK", "las vegas": "LAS",
    "san francisco": "SFO", "toronto": "YYZ", "yyz": "YYZ", "vancouver": "YVR",
    "yvr": "YVR", "boston": "BOS", "washington": "WAS", "washington dc": "WAS",
    "washington, d.c.": "WAS", "mexico city": "MEX", "cancun": "CUN", "cancún": "CUN",
    "sao paulo": "SAO", "são paulo": "SAO", "rio de janeiro": "RIO", "rio": "RIO",
    "buenos aires": "BUE", "cordoba": "COR", "córdoba": "COR", "bogota": "BOG",
    "bogotá": "BOG", "medellin": "MDE", "medellín": "MDE", "santiago": "SCL",
    "lima": "LIM", "cairo": "CAI", "riyadh": "RUH", "jeddah": "JED", "doha": "DOH",
    "muscat": "MCT", "tel aviv": "TLV", "larnaca": "LCA", "tehran": "THR",
    "mashhad": "MHD", "beirut": "BEY", "tokyo": "TYO", "osaka": "OSA", "beijing": "BJS",
    "shanghai": "SHA", "seoul": "SEL", "busan": "PUS", "hong kong": "HKG",
    "taipei": "TPE", "narita": "NRT", "incheon": "ICN", "sapporo": "CTS",
    "bangkok": "BKK", "bkk": "BKK", "chiang mai": "CNX", "jakarta": "JKT", "bali": "DPS",
    "denpasar": "DPS", "kuala lumpur": "KUL", "penang": "PEN", "manila": "MNL",
    "cebu": "CEB", "hanoi": "HAN", "ho chi minh city": "SGN", "saigon": "SGN",
    "singapore": "SIN", "lagos": "LOS", "abuja": "ABV", "nairobi": "NBO",
    "mombasa": "MBA", "johannesburg": "JNB", "cape town": "CPT", "casablanca": "CMN",
    "marrakech": "RAK", "marrakesh": "RAK", "addis ababa": "ADD",
    "delhi": "DEL", "new delhi": "DEL", "del": "DEL", "indore": "IDR", "idr": "IDR",
    "mumbai": "BOM", "bombay": "BOM", "bom": "BOM", "bengaluru": "BLR", "bangalore": "BLR",
    "blr": "BLR", "chennai": "MAA", "madras": "MAA", "kolkata": "CCU", "calcutta": "CCU",
    "goa": "GOA", "hyderabad": "HYD", "hyd": "HYD", "ahmedabad": "AMD", "kochi": "COK",
    "cochin": "COK", "thiruvananthapuram": "TRV", "trivandrum": "TRV", "dubai": "DXB",
    "london": "LON", "new york": "NYC", "pune": "PNQ", "guwahati": "GAU", "lucknow": "LKO",
    "varanasi": "VNS",
    # AIRPORT NAMES. The prompt tells the model to keep an airport's name when
    # the line names one, and the device resolves it: "Kempegowda" is BLR at
    # rank 2. Without these the eval scored a right answer as a miss.
    "kempegowda": "BLR", "kempegowda international": "BLR", "indira gandhi": "DEL",
    "indira gandhi international": "DEL", "chhatrapati shivaji": "BOM",
    "chhatrapati shivaji maharaj": "BOM", "rajiv gandhi": "HYD", "dabolim": "GOA",
    "mopa": "GOA", "heathrow": "LHR", "gatwick": "LGW", "stansted": "STN",
    "newark": "EWR", "laguardia": "LGA", "orly": "ORY", "charles de gaulle": "CDG",
    "haneda": "HND", "sheremetyevo": "SVO", "domodedovo": "DME", "vnukovo": "VKO",
    "linate": "LIN", "malpensa": "MXP", "dulles": "IAD", "reagan": "DCA",
    "ezeiza": "EZE", "aeroparque": "AEP", "congonhas": "CGH", "guarulhos": "GRU",
    "hongqiao": "SHA", "pudong": "PVG", "gimpo": "GMP", "don mueang": "DMK",
    "suvarnabhumi": "BKK", "sabiha gokcen": "SAW", "sabiha gökçen": "SAW",
    "istanbul airport": "IST",
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
# ── THE WORLD SET ─────────────────────────────────────────────────────────────
# (line, expected kind, expected origin, expected destination, expected date, expected number)
WORLD_CASES = [
    # Europe
    ("vuelos de madrid a barcelona mañana", R, "MAD", "BCN", d(1), None),
    ("vol paris nice demain matin", R, "PAR", "NCE", d(1), None),
    ("flüge von münchen nach berlin am freitag", R, "MUC", "BER", weekday("friday"), None),
    ("voli roma milano stasera", R, "ROM", "MIL", d(0), None),
    ("lot warszawa kraków jutro", R, "WAW", "KRK", d(1), None),
    ("москва питер завтра утром", R, "MOW", "LED", d(1), None),
    ("istanbul'dan ankara'ya uçuşlar", R, "IST", "ESB", None, None),
    ("lisboa porto sexta", R, "LIS", "OPO", weekday("friday"), None),
    # the Americas
    ("lax to jfk tomorrow", R, "LAX", "JFK", d(1), None),
    ("vegas to sf red eye", R, "LAS", "SFO", None, None),
    ("yyz yvr saturday", R, "YYZ", "YVR", weekday("saturday"), None),
    ("boston to dc early morning", R, "BOS", "WAS", None, None),
    ("vuelos cdmx a cancún", R, "MEX", "CUN", None, None),
    ("voos são paulo rio amanhã cedo", R, "SAO", "RIO", d(1), None),
    ("de buenos aires a córdoba el viernes", R, "BUE", "COR", weekday("friday"), None),
    ("vuelos bogotá medellín hoy", R, "BOG", "MDE", d(0), None),
    ("lima to santiago", R, "LIM", "SCL", None, None),
    # the Middle East
    ("رحلات من دبي إلى القاهرة غدا", R, "DXB", "CAI", d(1), None),
    ("riyadh to jeddah tonight", R, "RUH", "JED", d(0), None),
    ("doha muscat", R, "DOH", "MCT", None, None),
    ("tel aviv to larnaca", R, "TLV", "LCA", None, None),
    ("تهران به مشهد", R, "THR", "MHD", None, None),
    ("beirut istanbul saturday", R, "BEY", "IST", weekday("saturday"), None),
    # East Asia
    ("東京から大阪 明日", R, "TYO", "OSA", d(1), None),
    ("北京到上海的航班", R, "BJS", "SHA", None, None),
    ("서울 부산 내일 아침", R, "SEL", "PUS", d(1), None),
    ("hongkong taipei", R, "HKG", "TPE", None, None),
    ("narita to incheon", R, "NRT", "ICN", None, None),
    ("osaka sapporo", R, "OSA", "CTS", None, None),
    # Southeast Asia
    ("กรุงเทพ เชียงใหม่ พรุ่งนี้", R, "BKK", "CNX", d(1), None),
    ("penerbangan jakarta ke bali besok", R, "JKT", "DPS", d(1), None),
    ("kl to penang", R, "KUL", "PEN", None, None),
    ("manila cebu", R, "MNL", "CEB", None, None),
    ("hanoi saigon", R, "HAN", "SGN", None, None),
    ("sg to bkk tonight", R, "SIN", "BKK", d(0), None),
    # Africa
    ("lagos to abuja", R, "LOS", "ABV", None, None),
    ("nairobi mombasa tomorrow", R, "NBO", "MBA", d(1), None),
    ("joburg cape town", R, "JNB", "CPT", None, None),
    ("casablanca marrakech", R, "CMN", "RAK", None, None),
    ("addis to dubai", R, "ADD", "DXB", None, None),
]
assert len(WORLD_CASES) == 40, len(WORLD_CASES)
# THE COUNTRY HINT, where a line settles a name that exists in more than one
# country. Checked on these lines; a hint on any other line is printed as a
# guess and counted separately, because the prompt says never to guess one.
COUNTRIES = {
    "de buenos aires a córdoba el viernes": {"destination": "Argentina"},
    "lima to santiago": {"destination": "Chile"},
}
if WORLD:
    CASES = WORLD_CASES

# The one line among the forty that is a question, and what it asks.
QUESTIONS = {"when is the next flight to indore": "next"}
# A LINE THAT READS BOTH WAYS. "any flights X to Y tonight" is a request to see
# the board and a question about whether there is one; the model returned each
# reading on different runs, and both give a right board with, at most, a true
# sentence over it. Either is accepted.
QUESTION_EITHER = {"any flights kolkatta to guwahati tonight": {None, "count"}}

# (line, expected origin, expected destination, expected question)
QUESTION_CASES = [
    ("when is the next flight to indore", None, "IDR", "next"),
    ("next flight to indore?", None, "IDR", "next"),
    ("what is the first flight from delhi to mumbai tomorrow", "DEL", "BOM", "first"),
    ("when is the last flight from bangalore to delhi tonight", "BLR", "DEL", "last"),
    ("which is the fastest flight from mumbai to goa", "BOM", "GOA", "fastest"),
    ("what is the earliest I can get to chennai from hyderabad", "HYD", "MAA", "arrival"),
    ("how many flights are there from delhi to indore tomorrow", "DEL", "IDR", "count"),
    ("is there a flight from pune to goa on sunday", "PNQ", "GOA", "count"),
    ("which airlines fly delhi to indore", "DEL", "IDR", "airlines"),
    ("show me the fastest flight delhi to mumbai", "DEL", "BOM", None),
]


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
        got_q = intent.get("question")
        if line in QUESTION_EITHER:
            if got_q not in QUESTION_EITHER[line]:
                notes.append(f"question {got_q}")
        elif got_q != QUESTIONS.get(line):
            notes.append(f"question {got_q}")
        for end in ("origin", "destination"):
            want_c = COUNTRIES.get(line, {}).get(end)
            got_c = (intent.get(f"{end}_country") or "").strip()
            if want_c is not None and got_c.lower() != want_c.lower():
                notes.append(f"{end}_country {got_c!r} not {want_c!r}")
            elif want_c is None and got_c:
                GUESSED.append(f"{line}: {end} {got_c}")
    if kind == F and intent:
        if intent.get("flight_number") != num:
            notes.append(f"number {intent.get('flight_number')}")
        if day is not None and intent.get("date") != day:
            notes.append(f"date {intent.get('date')} not {day}")
    return notes


GUESSED = []
totals = {R: [0, 0], F: [0, 0], C: [0, 0]}
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
    intent = reply.get("intent")
    shown = (f"{intent['kind']}: {intent.get('origin')}->{intent.get('destination')} {intent.get('date') or ''} {intent.get('range_label') or ''}"
             f"{' ?' + intent['question'] if intent.get('question') else ''}"
             f"{' [' + ', '.join(c for c in (intent.get('origin_country'), intent.get('destination_country')) if c) + ']' if intent.get('origin_country') or intent.get('destination_country') else ''}".strip()
             if intent and intent["kind"] == "route" else
             f"flight: {intent.get('flight_number')} {intent.get('date') or ''}".strip() if intent else
             f"chat: {(reply.get('response') or reply.get('error') or '')[:60]!r}")
    flag = "  ok  " if not notes else "  MISS"
    rows.append(f"{flag} {case[0]:<52} {shown}" + (f"   <- {'; '.join(notes)}" if notes else "")
)

print("\n".join(rows))
print()
right = sum(v[0] for v in totals.values())
print(f"routes  {totals[R][0]}/{totals[R][1]}   flights {totals[F][0]}/{totals[F][1]}   chat {totals[C][0]}/{totals[C][1]}")
print(f"MISREAD RATE ({'world' if WORLD else 'first'} forty): {40 - right}/40 = {(40 - right) / 40:.1%}")
if GUESSED:
    print(f"country guessed where no line settled it ({len(GUESSED)}):")
    for g in GUESSED:
        print("   ", g)

if WORLD:
    sys.exit(0)
print()
qright = 0
for line, o, dst, q in QUESTION_CASES:
    try:
        reply = post(line)
    except Exception as exc:  # noqa: BLE001
        reply = {"error": f"transport: {exc}"}
    intent = reply.get("intent")
    notes = []
    if not intent or intent.get("kind") != "route":
        notes.append("not a route")
    else:
        if code(intent.get("origin")) != o:
            notes.append(f"origin {intent.get('origin')!r}")
        if code(intent.get("destination")) != dst:
            notes.append(f"dest {intent.get('destination')!r}")
        if intent.get("question") != q:
            notes.append(f"question {intent.get('question')} not {q}")
    if not notes:
        qright += 1
    got = intent.get("question") if intent else (reply.get("response") or reply.get("error") or "")[:40]
    print(("  ok  " if not notes else "  MISS") + f" {line:<58} {got!s:<10}" + (f"   <- {'; '.join(notes)}" if notes else ""))
print(f"QUESTION SHAPES: {qright}/{len(QUESTION_CASES)} read as intended")
