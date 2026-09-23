import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
# WHICH MODEL THIS SERVICE TALKS TO, AND THE ONE SHAPE IT TALKS IN.
#
# llm.py owns the provider choice, the credentials, the two model names, the
# translation of a request into whatever SDK is in use, and the classification
# of a failure. THE `import anthropic` THAT USED TO SIT HERE IS GONE WITH IT --
# this file no longer names a provider anywhere, which is the whole point of the
# translation layer and the one property worth protecting when editing it.
import llm
# THE ONLY THING PERMITTED TO SAY A FLIGHT HAS LANDED. Its own module for the
# same reason llm.py is one: a second vendor with its own credential, its own
# quota currency, its own error vocabulary and its own cache does not belong
# inside the AeroDataBox layer.
import fr24
# THE USER'S OWN GMAIL, read for upcoming flights. Its own module for the
# reasons the other two vendors have theirs, plus one more: it handles the
# contents of people's booking emails, and the rules for that -- never logged,
# never stored, truncated before the model sees them -- live in one file.
import gmail_flights
import auth
import re
from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import dispatch
import poller
import pollstate
import store
from mcp_server import (
    fetch_flight_full,
    extract_flight_number,
    fetch_route,
    quota_status,
    _validate_route_date,
    FLIGHT_MAX_FUTURE_DAYS,
)

load_dotenv()

# A CALENDAR DAY AND NOTHING ELSE. The same shape store.py and pollstate.py
# both match on; this file needed one of its own for the single endpoint that
# validates a date WITHOUT asking whether it is in the future.
_ISO_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ANTHROPIC_API_KEY IS GONE FROM THIS FILE, and on the default configuration
# it is not read at all: Vertex authenticates as the Cloud Run service
# account through Application Default Credentials, exactly as store.py's
# bucket client does. llm.py still reads the key for the anthropic provider,
# which is the rollback path and nothing else.

# Cloud Run captures stdout and stderr, so a module logger needs no handler and
# no configuration to reach the service logs. This is the first logging in the
# file: the reason a request failed used to exist only in the string sent back
# to the client, which is exactly the place a billing detail must not be.
logger = logging.getLogger("flight-tracker")

app = FastAPI()

# ONE ORIGIN, AND IT IS THE ONLY BROWSER THAT CALLS THIS SERVICE. The list was
# ["*", <this>], which is "*" -- the named entry never did anything, because a
# wildcard is checked first and matches everything.
#
# THE MOBILE APP IS NOT AFFECTED AND NEVER WAS. CORS is enforced by browsers,
# against browsers; a native app sends no Origin header and is never preflighted.
# Narrowing this cannot break iOS or Android, and widening it would not have
# helped them.
#
# NOR IS THIS A SECURITY CONTROL, and it must not be mistaken for one. curl, a
# script, or anything that is not a browser ignores every header below. What it
# stops is one specific thing: a page on some other domain making calls to this
# API from a visitor's browser. The secrets on the endpoints are what actually
# guard them.
#
# METHODS AND HEADERS ARE WHAT THE ROUTES IN THIS FILE ACTUALLY USE. Five GET
# routes and five POST, and no other verb exists here. OPTIONS is deliberately
# absent: the preflight check compares Access-Control-Request-Method, which
# carries the REAL method, and the middleware answers the OPTIONS request
# itself. Content-Type is the only header any caller sends, and starlette
# safelists it anyway -- it is written out so the intent is visible rather than
# inherited.
#
# allow_credentials IS LEFT UNSET, so it is False. Nothing here uses cookies,
# and the Gmail token /chat receives travels in the body rather than as a
# credential -- so this setting is not what protects it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flight-tracker-navy-eight.vercel.app"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# `origin` is the departure IATA the caller is asking about, and it exists for
# TAG FLIGHTS: one number operating consecutive legs on one day returns two
# instances that `date` cannot separate, because they share it. Absent is
# today's behaviour exactly — every MCP tool passes nothing and is unchanged.
#
# NOT VALIDATED HERE, deliberately, where `date` is. A malformed date would cost
# four units upstream, so it is worth rejecting early; a malformed origin costs
# nothing, because fetch_flight_full normalises anything that is not three
# letters to "no filter" and the call it would have made is the call it makes.
# One normalisation, in one place.
# ── fresh=1 GOES TO THE PROVIDER, AND NOTHING ELSE DOES ──────────────────────
#
# A MANUAL REFRESH ON A CARD MUST NOT BE ANSWERED FROM A COPY. fetch_flight_full
# keeps a five-minute cache, and it is the SAME cache the poller fills -- so a
# refresh thirty seconds after a poll came back with the poller's answer and
# called it fresh. For a passive reader that is the point of the cache; for
# somebody who pressed a button to be told what is true now, it is the app
# declining to look.
#
# max_age ZERO IS A GUARANTEED MISS, and it costs what a miss costs: two units,
# every time. That is the price of the button meaning what it says. The answer
# it fetches then fills the cache, so the next poll inside five minutes is free.
@app.get("/flight/{flight_number}")
def get_flight(flight_number: str, date: str | None = None, origin: str | None = None,
               fresh: bool = False):
    # The same validator the route search uses, so the two cannot drift on what
    # a date means -- but with the FLIGHT ceiling, which the provider puts at 180
    # days on this plan where the board's is 60. See FLIGHT_MAX_FUTURE_DAYS.
    # Every rejection happens here, before any upstream call.
    day, date_error = _validate_route_date(date, max_future=FLIGHT_MAX_FUTURE_DAYS)
    if date_error is not None:
        return {"error": date_error}
    _text, dto = fetch_flight_full(flight_number, day, origin,
                                   max_age=timedelta(0) if fresh else None)
    if dto is None:
        suffix = f" on {day}" if day else ""
        return {"error": f"No flight found for {flight_number.strip().upper()}{suffix}"}
    return dto


@app.get("/route/{origin}/{destination}")
def get_route(origin: str, destination: str, hours: int = 12, date: str | None = None):
    return fetch_route(origin, destination, hours, date)


# ──────────────────────────────────────────────
# HAS IT LANDED
# ──────────────────────────────────────────────
#
# ITS OWN ENDPOINT RATHER THAN A FIELD ON /flight, AND THE REASON IS BUDGETS.
# The two providers are billed in different currencies with very different
# scarcity: AeroDataBox units are the scarce one, FR24 credits are not. Folding
# the landing check into /flight would mean every five-minute check near an
# arrival also spent an AeroDataBox unit -- roughly forty of them per flight --
# so the constrained budget would be paying for the unconstrained one.
#
# IT ALSO MEANS FR24 CANNOT SLOW OR BREAK /flight. Schedules, gates, terminals
# and route search are structurally out of reach of an FR24 outage, which is
# the property that lets the whole thing degrade to yesterday's behaviour.
#
# NO SECRET AND NO WRITE. This is a read of a public-ish fact about a flight
# number, exactly like /flight beside it, and it changes nothing on the server.
@app.get("/landing/{flight_number}")
def get_landing(flight_number: str, date: str | None = None, dest: str | None = None,
                dep: str | None = None, reg: str | None = None):
    """Whether Flightradar24 says this flight has landed, and when.

    dest  destination IATA -- what separates the two legs of a tag flight.
    dep   scheduled departure as an ISO instant. Optional and worth sending:
          it narrows the search window from about two days to about one leg,
          and FR24 bills per returned record.
    reg   aircraft registration, used only to break a tie.
    """
    day, date_error = _validate_route_date(date, max_future=FLIGHT_MAX_FUTURE_DAYS)
    if date_error is not None:
        return {"error": date_error}
    result = fr24.landing_for(
        flight_number,
        date=day,
        destination_iata=dest,
        departure_utc=dep,
        registration=reg,
    )
    # THE OUTCOME TRAVELS VERBATIM, INCLUDING THE FAILURES. A caller has to be
    # able to tell "asked and does not know" from "could not ask" -- the first
    # lets AeroDataBox's own arrival stand and the second must not. Flattening
    # an error into a null would hand the decision back to the provider this
    # endpoint exists to overrule.
    return result


# Its own endpoint, deliberately, rather than a key on the route and flight
# envelopes. Those answer "what is this search", and a cached one involves no
# provider call at all — a units figure sitting in that payload would read as
# measured now when it could be hours old. Here the age travels with the number.
# Costs nothing: it reports what earlier calls already told us.
@app.get("/quota")
def get_quota():
    # FR24 TRAVELS ALONGSIDE IT RATHER THAN IN IT. The two are different
    # currencies -- AeroDataBox reports units remaining on every response, FR24
    # reports nothing and would have to be asked at the cost of a credit -- so
    # this half is not a balance. It is whether the breaker is open, which is
    # the question actually worth answering in an outage: a run of cards that
    # stop reaching 'landed' looks identical to a quiet day until you can see
    # that every call has been failing.
    return {**quota_status(), "fr24": fr24.breaker_status()}


TOOLS = [
    {
        "name": "check_my_flight",
        "description": (
            "Smart flight status checker. "
            "If a flight number is given (e.g. AI2630), check it directly. "
            "If the question is vague (e.g. 'what's my flight status?'), "
            "read the user's upcoming flights out of their Gmail and check the soonest one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's question or flight number"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_flight_status",
        "description": "Get the current status of a flight by its IATA flight number e.g. AI2630, 6E5031",
        "input_schema": {
            "type": "object",
            "properties": {
                "flight_number": {"type": "string", "description": "IATA flight number e.g. AI2630"}
            },
            "required": ["flight_number"],
        },
    },
    {
        "name": "find_flight_from_gmail",
        "description": "Read the user's upcoming flights out of their Gmail and check the soonest one. Use this only when the user asks about their own flight without giving a flight number.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def run_tool(name: str, inputs: dict, gmail_token: str = None) -> tuple[str, dict | None]:
    if name == "check_my_flight":
        flight_number = extract_flight_number(inputs["query"])
        if flight_number:
            return fetch_flight_full(flight_number)
        if not gmail_token:
            return ("No flight number provided and you're not signed in with Google. Please sign in or provide a flight number directly.", None)
        return _soonest_from_gmail(gmail_token)
    if name == "get_flight_status":
        return fetch_flight_full(inputs["flight_number"])
    if name == "find_flight_from_gmail":
        if not gmail_token:
            return ("You need to sign in with Google first so I can access your Gmail.", None)
        return _soonest_from_gmail(gmail_token)
    return (f"Unknown tool: {name}", None)


def _soonest_from_gmail(gmail_token: str) -> tuple[str, dict | None]:
    """The assistant's Gmail path: the next leg to depart, looked up ON ITS DATE.

    The old path handed fetch_flight_full a bare number and let the provider
    pick the day. The extractor knows the date, so the lookup is dated and a
    booking for the 20th is not answered with today's instance of the same
    number. The tool result names the other legs so the model can mention them.
    """
    r = gmail_flights.upcoming_flights(gmail_token)
    if not r["ok"]:
        return (GMAIL_ERRORS.get(r["code"], GMAIL_ERROR_GENERIC), None)
    first = gmail_flights.soonest(r["flights"])
    if first is None:
        return ("No upcoming flight bookings found in your Gmail.", None)
    text, dto = fetch_flight_full(first["flight_number"], first["date"], first.get("origin"))
    others = [f"{f['flight_number']} on {f['date']}" for f in r["flights"][1:5]]
    if others:
        text = text + "\nOther upcoming flights in Gmail: " + ", ".join(others)
    return (text, dto)


# HUNK 5. The tool set is three tools deep and the longest honest path is two
# rounds: find the number in Gmail, then look that number up, then answer. Four
# leaves room for one wrong turn and still terminates. Each round is a full
# model call, so an uncapped loop is a bill and a hung request, not just a bug.
CHAT_MAX_TOOL_ROUNDS = 4

# 4096, AND IT WAS 1024 UNTIL A MEASUREMENT MOVED IT. Gemini 3 bills its own
# reasoning against this ceiling, and "is EK648 on time" -- a lookup and a
# reformat, the least demanding thing this endpoint does -- spent 992 tokens
# thinking and 82 answering. 1024 would have truncated it.
#
# THINKING STAYS ON HERE, unlike /parse. Choosing which of three tools to call,
# and whether the answer needs a second round, is the one judgement in this
# service that reasoning plausibly improves -- so this endpoint buys the room
# rather than turning it down.
CHAT_MAX_TOKENS = 4096

# HUNK 4. What the app is allowed to show. Fixed strings, never the provider's
# own message: an upstream error can quote a key, an account identifier or an
# internal endpoint, and none of that may reach a client.
CHAT_ERROR_GENERIC = "The assistant is unavailable right now. Please try again."
CHAT_ERROR_BUSY = "The assistant is busy right now. Please try again in a moment."
# Deliberately WORD FOR WORD the generic string. Credit exhaustion is a billing
# fact about the operator's account, and a user who reads it can do nothing with
# it except learn something that is none of their business. The branch survives
# so the LOG can still say which failure it was — see _chat_error.
CHAT_ERROR_CREDIT = "The assistant is unavailable right now. Please try again."
CHAT_ERROR_CONFIG = "The assistant is not configured correctly."
CHAT_ERROR_TOO_MANY_STEPS = (
    "The assistant took too many steps to answer that. Please rephrase and try again."
)


class ChatRequest(BaseModel):
    message: str
    gmail_token: str | None = None


class IntentRequest(BaseModel):
    message: str
    gmail_token: str | None = None
    # THE DEVICE'S OWN CALENDAR DATE, YYYY-MM-DD. "Tomorrow" is the user's
    # tomorrow, and at 23:30 in Mumbai that is not the server's. Omitted, the
    # server's UTC date stands in, which is what /parse always used.
    today: str | None = None
    # WHETHER THE DEVICE FOUND A PLACE IN THE SENTENCE -- lib/airports.ts's
    # isKnownPlace, which the server cannot run. Measured for a forced second
    # reading that was retired (see the note above /intent) and kept in the
    # contract so the device need not change when the server next wants it.
    has_place: bool = False


class GmailFlightsRequest(BaseModel):
    gmail_token: str | None = None


# ──────────────────────────────────────────────
# UPCOMING FLIGHTS, FROM GMAIL
# ──────────────────────────────────────────────
#
# ITS OWN ENDPOINT RATHER THAN A /chat TOOL, for three reasons. It returns a
# LIST -- one booking email holds three legs -- and /chat is built around one
# flight card. It fans out to up to ten model calls, which does not belong
# inside a tool loop capped at four rounds. And the app needs structured legs
# to offer "look this one up", not prose.
#
# THE TOKEN TRAVELS IN THE BODY, as it does for /chat, and it is never logged.
#
# FIXED STRINGS OUT, CODES BESIDE THEM. The app switches on `code` -- an expired
# sign-in has to clear the stored token and ask for another, which no sentence
# can tell it to do -- and shows the string. Neither is ever the provider's own
# text.
GMAIL_ERROR_GENERIC = "Could not read your Gmail right now. Please try again."
GMAIL_ERRORS = {
    gmail_flights.EXPIRED: "Your Google sign-in has expired. Sign in again to pull flights from Gmail.",
    gmail_flights.FORBIDDEN: "Terminal was not given permission to read your Gmail. Sign in again and allow it.",
    gmail_flights.BUSY: "Gmail is busy right now. Please try again in a moment.",
    gmail_flights.ERROR: GMAIL_ERROR_GENERIC,
}


# ── THE FIXTURE INBOX ────────────────────────────────────────────────────────
#
# OFF UNLESS GMAIL_FIXTURE_TOKEN IS SET ON THE SERVICE, and then only for a
# request whose token is exactly "fixture:<that value>". The seven synthetic
# emails in tools/gmail_fixtures stand in for the mailbox and everything from
# decoding onward is the real path, model calls included -- which is why it is
# a secret and not a flag: an open fixture endpoint is an open model bill.
# Unset in production, it is a dead branch.
GMAIL_FIXTURE_TOKEN = os.getenv("GMAIL_FIXTURE_TOKEN")


def _is_fixture_token(token: str) -> bool:
    if not GMAIL_FIXTURE_TOKEN or not token.startswith("fixture:"):
        return False
    return _secret_ok(token[len("fixture:"):], GMAIL_FIXTURE_TOKEN)


# ── THE SESSION, AND THE ACCESS TOKEN IT STANDS FOR ─────────────────────────
#
# THE APP NO LONGER HOLDS A GOOGLE TOKEN. It holds a session (see auth.py) and
# sends it as a Bearer header; this server turns it into a Google access token,
# minting one with the refresh grant when the stored one has expired. The
# fixture inbox rides the same header: "fixture:<secret>" in place of a session.
#
# THE BODY FIELD gmail_token IS THE OLD APP. A raw access token from the implicit
# flow, accepted for ONE RELEASE so an un-updated phone keeps working until its
# hour-long token expires and the app asks it to sign in again -- through the
# new flow. Remove the field, and this branch, in the release after.
def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization") or ""
    if h[:7].lower() != "bearer ":
        return None
    v = h[7:].strip()
    return v or None


def _gmail_access(request: Request, legacy_token: str | None) -> tuple[str | None, str | None]:
    """(token, code). token is a Google access token, or the fixture token."""
    session = _bearer(request)
    if session:
        if _is_fixture_token(session):
            return session, None
        return auth.access_token(session)
    if legacy_token:
        return legacy_token, None
    return None, gmail_flights.EXPIRED


class AuthGoogleRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


# Fixed strings, as GMAIL_ERRORS are: the app shows them and switches on the code.
AUTH_ERRORS = {
    auth.BAD_REQUEST: "The sign-in did not complete. Please try again.",
    auth.REJECTED: "Google did not accept the sign-in. Please try again.",
    auth.NO_REFRESH: "Google did not grant lasting access. Sign in again and allow Terminal to keep it.",
    auth.UNAVAILABLE: "Sign-in is not available right now. Please try again in a moment.",
}


@app.post("/auth/google")
def auth_google(req: AuthGoogleRequest):
    """The code, the verifier and the redirect in; a session, the email and a
    first name out. The email and name are returned once and not stored."""
    try:
        r = auth.sign_in(req.code, req.code_verifier, req.redirect_uri)
    except Exception:
        # The traceback goes to the log; auth.py logs no secret and this
        # catches only what it missed.
        logger.exception("auth: sign-in failed")
        r = {"ok": False, "code": auth.UNAVAILABLE}
    if not r["ok"]:
        return {"error": AUTH_ERRORS.get(r["code"], AUTH_ERRORS[auth.UNAVAILABLE]), "code": r["code"],
                "session": None, "email": None, "name": None, "gmail": False}
    return {"error": None, "code": None, "session": r["session"], "email": r["email"],
            "name": r["name"], "gmail": r["gmail"]}


@app.post("/auth/signout")
def auth_signout(request: Request):
    """Every session of the account, the record, and the grant at Google.
    Idempotent: a session that is already gone is a success."""
    session = _bearer(request)
    removed = False
    if session and not _is_fixture_token(session):
        try:
            removed = auth.sign_out(session)
        except Exception:
            logger.exception("auth: sign-out failed")
    return {"ok": True, "removed": removed}


@app.post("/gmail/flights")
def gmail_flights_endpoint(req: GmailFlightsRequest, request: Request):
    token, code = _gmail_access(request, req.gmail_token)
    if token is None:
        return {"error": GMAIL_ERRORS.get(code, GMAIL_ERROR_GENERIC), "code": code, "flights": []}
    try:
        if _is_fixture_token(token):
            logger.warning("gmail flights: serving the FIXTURE inbox")
            r = gmail_flights.upcoming_flights(
                token, lister=gmail_flights.fixture_lister, fetch=gmail_flights.fixture_fetch)
        else:
            r = gmail_flights.upcoming_flights(token)
    except Exception:
        # The traceback goes to the log. Nothing from the mailbox is in it: the
        # module logs counts and codes only, and this catches what it missed.
        logger.exception("gmail flights failed")
        return {"error": GMAIL_ERROR_GENERIC, "code": gmail_flights.ERROR, "flights": []}
    if not r["ok"]:
        return {"error": GMAIL_ERRORS.get(r["code"], GMAIL_ERROR_GENERIC), "code": r["code"], "flights": []}
    # cancelled_bookings RIDES BESIDE THE LEGS AND IS NOT ONE. Every error
    # return above carries flights only; a client that finds the key missing
    # reads it as "no booking was cancelled", which is what an error means
    # here -- nothing was learned either way.
    return {"error": None, "code": None, "flights": r["flights"],
            "cancelled_bookings": r.get("cancelled_bookings", []),
            "scanned": r["scanned"], "extracted": r["extracted"]}


class ParseRequest(BaseModel):
    message: str


# ──────────────────────────────────────────────
# STRUCTURED EXTRACTION
# ──────────────────────────────────────────────
#
# A sentence in, fields out. Never prose — that is what /chat is for, and the
# two must not share an endpoint: /chat's whole system prompt is about SHAPING
# TERMINAL TEXT, it carries three flight tools, and it returns a string plus an
# optional flight card. An extractor wants none of that and wants a schema
# instead, so one endpoint serving both would mean one system prompt serving two
# incompatible goals.
#
# PLACE NAMES, NEVER CODES, and this is the load-bearing decision in the whole
# feature. The model reads "san fransisco" and returns "San Francisco"; the
# DEVICE turns that into SFO against the bundled dataset. So the model cannot
# invent an airport, cannot reach one that is not in the app's own data, and
# cannot route around the on-device rejection of codes that do not exist. It
# segments a sentence. It does not choose a destination.
#
# ONE TURN, NO TOOL LOOP. There is nothing to look up: the airports live on the
# device, the date window is checked here and again there, and the vocabularies
# are closed and enforced by the schema below. A loop would add rounds and
# failure modes to a task with no external dependency.
# THE MODEL NAME MOVED TO llm.py, where it is read from the environment. It
# was a literal here, and a literal is the one form that cannot be corrected
# without a deploy -- which matters more than usual for this pair of names,
# because a PINNED SNAPSHOT spells its date differently on each provider:
# claude-haiku-4-5-20251001 on Anthropic direct is claude-haiku-4-5@20251001
# on Vertex. See the note there.
#
# THE TOKEN CEILING STAYS HERE. It is a fact about this prompt -- one forced
# tool call against a small closed schema -- rather than about the provider.
PARSE_MAX_TOKENS = 256

# Forced tool use rather than "reply with JSON". The schema is the contract: the
# enums make an out-of-vocabulary band or sort a malformed call rather than a
# plausible-looking string this file would then have to police.
PARSE_TOOL = {
    "name": "flight_search",
    "description": "Record the flight search described by the user's sentence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": (
                    "The departure CITY OR AIRPORT NAME, corrected for spelling, "
                    "in English. Never an IATA code. Omit if the sentence does not "
                    "say where the flight leaves from."
                ),
            },
            "destination": {
                "type": "string",
                "description": (
                    "The arrival CITY OR AIRPORT NAME, corrected for spelling, in "
                    "English. Never an IATA code. Omit if not stated."
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "The single calendar date asked for, as YYYY-MM-DD, resolved "
                    "against today's date given in the system prompt. Omit if no "
                    "date is mentioned, or if the sentence names a RANGE."
                ),
            },
            "date_kind": {
                "type": "string",
                "enum": ["single", "range"],
                "description": (
                    "'range' when the sentence names more than one day - 'this "
                    "weekend', 'next week', 'early October'. Set this INSTEAD of "
                    "date for those. Never collapse a range to one day."
                ),
            },
            "band": {
                "type": "string",
                "enum": ["morning", "afternoon", "evening", "overnight"],
                "description": "Departure time of day, if the sentence names one.",
            },
            "sort": {
                "type": "string",
                "enum": ["fastest", "earliest"],
                "description": "Requested ordering, if the sentence asks for one.",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "0 to 1. How confident you are that this sentence is a flight "
                    "search and that you have read it correctly. Be strict: a "
                    "sentence that might be a question about an existing booking "
                    "is not a search."
                ),
            },
        },
        "required": ["confidence"],
    },
}

# WHAT THE SEARCH BOX MAY SAY, and it is a SEPARATE VOCABULARY from /chat's
# rather than a share of it. These strings do not surface as an error banner:
# nlReadReply passes them to dead(), so whatever is here is rendered as the
# READING of the sentence the user just typed. "The assistant is not
# configured correctly" in that slot names a feature that is not on this
# screen, for a failure the user cannot act on.
#
# TWO KINDS OF FAILURE, AND THEY MUST NOT SHARE A STRING. "Could not read
# that" blames the SENTENCE, and it is the honest answer only when the model
# answered and the answer was unusable. When the call never completed the
# sentence was never the problem, and saying it was would send the user off
# rewording a perfectly good query against a service that is down.
PARSE_ERROR_GENERIC = "Could not read that as a flight search. Please try again."
PARSE_ERROR_UNAVAILABLE = "Flight search is unavailable right now. Please try again."
PARSE_ERROR_BUSY = "Flight search is busy right now. Please try again in a moment."


def _parse_clean(raw: dict, today) -> dict:
    """The model's fields, re-checked here before they leave the process.

    Nothing is trusted: the enums are re-tested, the date is re-parsed and
    re-bounded, and confidence is clamped. The device checks all of it AGAIN,
    because two cheap checks in different places is how a hallucinated field
    fails to become a four-unit search of the wrong day.
    """
    def s(key):
        v = raw.get(key)
        v = str(v).strip() if isinstance(v, str) else ""
        return v or None

    band = s("band")
    if band not in ("morning", "afternoon", "evening", "overnight"):
        band = None
    sort = s("sort")
    if sort not in ("fastest", "earliest"):
        sort = None
    kind = s("date_kind")
    if kind not in ("single", "range"):
        kind = None

    date = s("date")
    if date is not None:
        # The route validator, so this cannot drift from what /route will accept.
        day, err = _validate_route_date(date)
        date = None if err is not None else day
    # A range never carries a date, whatever the model put in the field.
    if kind == "range":
        date = None

    try:
        conf = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    return {
        "origin": s("origin"),
        "destination": s("destination"),
        "date": date,
        "date_kind": kind,
        "band": band,
        "sort": sort,
        "confidence": conf,
        "error": None,
    }


def _parse_empty(error=None) -> dict:
    return {
        "origin": None, "destination": None, "date": None, "date_kind": None,
        "band": None, "sort": None, "confidence": 0.0, "error": error,
    }


@app.post("/parse")
def parse(req: ParseRequest):
    text = str(req.message or "").strip()
    if not text:
        return _parse_empty(PARSE_ERROR_GENERIC)

    today = datetime.now(timezone.utc).date()
    system = (
        "You extract the fields of a flight search from one sentence. "
        f"Today is {today.isoformat()}. "
        "Call the flight_search tool exactly once and say nothing else.\n"
        "Return place NAMES, never airport codes: the caller resolves names "
        "itself and will reject a code.\n"
        "Correct obvious misspellings of place names.\n"
        "Omit any field the sentence does not state. Do not guess a departure "
        "city that was not given.\n"
        "If the sentence names more than one day, set date_kind to 'range' and "
        "omit date. Never pick one day out of a range."
    )

    try:
        turn = llm.generate(
            model=llm.PARSE_MODEL,
            system=system,
            messages=[llm.user_text(text)],
            tools=[PARSE_TOOL],
            # THE FORCED CALL IS THE WHOLE CONTRACT. The schema's enums are what
            # keep a band or a sort inside a closed vocabulary, and they only
            # apply to a TOOL CALL -- a model answering in prose is a model this
            # endpoint cannot use. Both providers can compel one; llm.py knows
            # how each spells it.
            forced_tool="flight_search",
            max_tokens=PARSE_MAX_TOKENS,
            # DETERMINISM, KEPT RATHER THAN DROPPED, because this path
            # re-validates every field the model returns -- see _parse_clean --
            # and that distrust of variance is the same argument for not
            # inviting any.
            temperature=0,
            # THINKING DOWN, AND THIS ONE IS NOT A PREFERENCE. Gemini 3 bills
            # reasoning against max_tokens: at 256 it spent 489 tokens thinking,
            # ran out mid-call and returned MALFORMED_FUNCTION_CALL with nothing
            # usable -- a 100% failure rate that would have surfaced as "could
            # not read that as a flight search" and sent somebody debugging the
            # parser. Minimised, the same call fits inside 256 with room over.
            #
            # AND IT COSTS NOTHING TO TURN DOWN. This is extraction against a
            # closed schema with the answer already in the sentence; there is no
            # judgement here for reasoning to improve.
            thinking=False,
        )
    except Exception as exc:
        # The same wording POLICY as /chat -- a fixed string out, the real reason
        # into the log, never the provider's own text -- and deliberately not the
        # same STRINGS. See _parse_error.
        return _parse_empty(_parse_error(exc))

    # THE TOOL CALL IS NAMED rather than taken positionally. Forcing guarantees
    # a call, not which one, and a model that invented a second tool would
    # otherwise be read as having answered the question asked.
    call = next((c for c in turn.tool_calls if c.name == "flight_search"), None)
    if call is None:
        logger.warning("parse call returned no flight_search call")
        return _parse_empty(PARSE_ERROR_GENERIC)

    return _parse_clean(call.args, today)


def _failure_kind(exc: Exception, feature: str) -> str:
    """Classify a failed model call, and log it. Never returns a user string.

    WHAT WENT WRONG AND WHAT TO SAY ABOUT IT ARE TWO QUESTIONS, and they were
    one function until /parse started borrowing /chat's answer to the second.
    This half is provider knowledge -- which exception means what -- and it is
    identical for every caller. The other half is a fact about the SCREEN the
    failure will appear on, and it is not.

    Returns one of 'config', 'busy', 'credit', 'generic'. The caller maps that
    to its own wording; the mapping is the caller's because the words are.

    `feature` names the endpoint in the log line and nothing else. It never
    reaches the client.

    WHICH EXCEPTION MEANS WHAT IS llm.py's, and this function is what is left
    once that moved: the logging, and the endpoint's name in the log line. The
    two SDKs disagree far too deeply for the test to live here -- Anthropic
    raises a class per failure, Google raises one class and puts the failure in
    a status code -- and an endpoint is the wrong place to know that.

    THE REASON STRING IS THE PROVIDER'S, THE WORDS ARE NOT. llm.failure_kind
    returns a short phrase written for this log line, never the provider's own
    message, which can quote a key, an account identifier or an endpoint.
    """
    kind, reason = llm.failure_kind(exc)
    logger.warning("%s call failed: %s", feature, reason)
    return kind


def _chat_error(exc: Exception) -> str:
    """One of the CHAT_ERROR strings. Never the exception's own text."""
    return {
        "config": CHAT_ERROR_CONFIG,
        "busy": CHAT_ERROR_BUSY,
        "credit": CHAT_ERROR_CREDIT,
    }.get(_failure_kind(exc, "assistant"), CHAT_ERROR_GENERIC)


def _parse_error(exc: Exception) -> str:
    """One of the PARSE_ERROR strings. Never the exception's own text.

    NOTHING HERE SAYS "ASSISTANT", and that is the whole reason this function
    exists. /parse used to return _chat_error's strings, so a misconfigured
    provider told somebody typing "flights to goa tomorrow" that the assistant
    was not configured correctly -- a screen they were not on, about a feature
    they had not used, in place of the reading of their sentence.

    A MISCONFIGURATION IS NOT REPORTED AS ONE. 'config' means an operator has
    something to fix and the user has nothing to do but wait, which is what
    "unavailable" says. The distinction survives where it is useful: in the log,
    where _failure_kind already put it.

    AND NONE OF THESE IS PARSE_ERROR_GENERIC. Every kind here is a call that did
    not complete, so the sentence was never the problem. That string belongs to
    the one case where the model DID answer and the answer was unusable -- see
    the missing tool_use block at the call site.
    """
    return {
        "busy": PARSE_ERROR_BUSY,
    }.get(_failure_kind(exc, "parse"), PARSE_ERROR_UNAVAILABLE)


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    messages = [llm.user_text(req.message)]
    # Resolved once, up front, so a chat that never touches Gmail never asks
    # Google for anything. None means the tools answer "not signed in".
    gmail_access, _gmail_code = _gmail_access(request, req.gmail_token)

    system = (
        "You are a terminal-based flight assistant. "
        "Format all responses as plain terminal output — no emojis, no markdown, no bold, no headers, no tables. "
        "Each piece of information must be on its own line in plain text. "
        "Use lowercase labels followed by a colon, like:\n"
        "EK648 — Emirates\n"
        "status: active\n"
        "departure: Dubai (DXB) terminal 3, gate C12\n"
        "scheduled departure: 4:10 PM GMT+4\n"
        "arrival: Colombo (CMB) terminal main\n"
        "scheduled arrival: 10:10 PM GMT+5:30\n"
        "Always reproduce the timezone label exactly as the flight tool returns it for each time. "
        "Never substitute, convert, or invent a timezone label.\n"
        "If a time is followed by the qualifier (predicted), reproduce that qualifier exactly as written and never drop it.\n"
        "Keep responses concise. Output must be suitable for a monospace terminal display."
    )

    captured_flight = None

    for _round in range(CHAT_MAX_TOOL_ROUNDS):
        try:
            # NO SAMPLING PARAMETER HERE, ON ANY PROVIDER. Claude Sonnet 5
            # rejects a non-default temperature, top_p or top_k with a 400, and
            # the models after it reject even the default; the anthropic SDK
            # raises a TypeError before the request is even sent. /parse passes
            # temperature deliberately because it runs on a model that accepts
            # one -- that is a fact about that model, not a pattern to copy.
            turn = llm.generate(
                model=llm.CHAT_MODEL,
                system=system,
                messages=messages,
                tools=TOOLS,
                max_tokens=CHAT_MAX_TOKENS,
            )
        except Exception as exc:
            # The app renders `error`; without this the exception escaped as a
            # bare 500 whose body has no `error` key at all, which is why every
            # failure looked like "Something went wrong".
            return {"error": _chat_error(exc), "response": None, "flight": captured_flight}

        # TOOL CALLS FIRST, AND THE ORDER IS THE WHOLE CHANGE HERE. This used to
        # ask WHY the model stopped and treat "tool_use" as the branch that runs
        # tools -- which is Anthropic's vocabulary and nobody else's. Gemini ends
        # a turn carrying function calls with an ordinary STOP, so a loop that
        # branches on the stop reason runs no tools at all and returns empty
        # text. Asking what is IN the turn is the question both providers answer
        # the same way.
        if turn.tool_calls:
            results = []
            for call in turn.tool_calls:
                result_text, flight_data = run_tool(call.name, call.args, gmail_access)
                if flight_data is not None:
                    captured_flight = flight_data
                results.append((call, result_text))
            # THE MODEL'S OWN TURN GOES BACK VERBATIM. On Gemini 3 the parts
            # carry thought signatures which the next round requires; rebuilding
            # the turn from its text and its calls drops them silently. llm.py
            # keeps the provider's object for exactly this.
            messages.append(llm.model_turn(turn))
            messages.append(llm.tool_results(results))
            continue

        # NO CALLS, SO THIS IS THE ANSWER -- whether the model finished cleanly,
        # hit a ceiling, or refused. If it said anything at all, that is better
        # than a canned line.
        if turn.text:
            return {"response": turn.text, "flight": captured_flight}
        return {"error": CHAT_ERROR_GENERIC, "response": None, "flight": captured_flight}

    # The loop ran out of rounds. Anything already found still goes back, so a
    # flight the tools did retrieve is not thrown away with the conversation.
    return {
        "error": CHAT_ERROR_TOO_MANY_STEPS,
        "response": None,
        "flight": captured_flight,
    }


# ──────────────────────────────────────────────
# INTENT: ONE CALL, WHATEVER WAS TYPED
# ──────────────────────────────────────────────
#
# THE COMMAND LINE HAD TWO PAID RUNGS WITH DIFFERENT CONTRACTS -- /parse
# extracted fields and made the user press twice, /chat talked -- and a gate
# between them that guessed which one a sentence deserved. The gate guessed
# wrong in both directions: a sentence whose only place was "delhi" never
# reached the extractor, and one with no origin reached it and stopped dead.
#
# THIS IS THE ONE RUNG THAT REPLACES BOTH. The model reads the line and either
# calls search_route or lookup_flight -- a STRUCTURED INTENT, which is returned
# to the device and NOT executed here -- or runs the Gmail tool and answers, or
# simply answers. Whatever it does, something comes back that the screen can
# show. Nothing here spends a provider unit on a search: the device runs every
# intent through the same code its free rungs use, against its own dataset.
#
# THE MODEL STILL NEVER CHOOSES AN AIRPORT. It returns place NAMES with the
# spelling corrected, and the device resolves them against the bundled data,
# exactly as /parse did. That is what stops it inventing an airport, and it is
# kept on purpose. The one relaxation: a 3-letter code the USER typed comes back
# as typed, because the device resolves codes at rank 0 and a code somebody
# wrote is not an invention.
#
# ── THE FORCED RETRY, MEASURED AND RETIRED ─────────────────────────────────
#
# The first build asked once more, with search_route forced, whenever the first
# turn was prose and the device said the sentence named a place -- against the
# day Gemini answers a route request in words. tools/eval_intent.py measured it
# over two runs of the forty: it fired twice, both times on "what is the weather
# in delhi", never on a route, and the second time it returned a confident
# route to Delhi that nobody asked for. A forced call always produces a call,
# and the model's confidence in one is not evidence. The prose the model gave
# first was the right answer both times, so the prose is the answer, and
# has_place stays in the request as a measured fact the server may yet want.
# WHAT A LINE CAN ASK ABOUT A BOARD, beyond wanting to see it. The device answers
# each from the board it fetched, on the line above the results: the extreme row
# under the key the question names, or a count, or the carriers. A shape not in
# this tuple is dropped, like every other enum the model returns.
INTENT_QUESTIONS = ("next", "first", "last", "fastest", "arrival", "count", "airlines")
INTENT_EMPTY = "type a flight number, a route like delhi to indore, or a question"
INTENT_NO_DESTINATION = "I could not tell where you are flying to. Try: delhi to indore"
INTENT_BAD_NUMBER = "I could not read a flight number in that. Try: 6E5071"

INTENT_ROUTE_TOOL = {
    "name": "search_route",
    "description": (
        "The user wants to see flights between two places. Call this for ANY "
        "request to see, list, find or compare flights from one place to "
        "another, however it is phrased or misspelt, including bare codes like "
        "'DEL IDR' or 'del/idr'. Do not answer such a request in words."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": (
                    "Where the flight leaves from: the city or airport NAME in "
                    "English with spelling corrected (Delhi, Indore), or the "
                    "3-letter code if the user typed a code. OMIT ENTIRELY if the "
                    "sentence does not say -- never guess; the app knows the "
                    "user's location."
                ),
            },
            "destination": {
                "type": "string",
                "description": "Where the flight goes, same rules as origin. Required.",
            },
            "origin_country": {
                "type": "string",
                "description": (
                    "The origin's country, in English (India, Chile, United States), "
                    "ONLY when the city's name exists in more than one country AND "
                    "the sentence says or implies which. Otherwise omit; never guess."
                ),
            },
            "destination_country": {
                "type": "string",
                "description": "The destination's country, same rule as origin_country.",
            },
            "date": {
                "type": "string",
                "description": (
                    "YYYY-MM-DD, resolved against today's date in the system "
                    "prompt. For a RANGE ('this weekend', 'next week', 'early "
                    "October') give the FIRST day of the range and set date_kind "
                    "to 'range'. Omit if no day is mentioned."
                ),
            },
            "date_kind": {"type": "string", "enum": ["single", "range"]},
            "range_label": {
                "type": "string",
                "description": "The user's own words for the range, e.g. 'this weekend'. Only with date_kind 'range'.",
            },
            "band": {
                "type": "string",
                "enum": ["morning", "afternoon", "evening", "overnight"],
                "description": "Departure time of day, if named. Red-eye, late night and early morning are 'overnight'.",
            },
            "sort": {
                "type": "string",
                "enum": ["fastest", "earliest"],
                "description": "fastest/quickest/shortest -> fastest; earliest/first/soonest/next -> earliest.",
            },
            "question": {
                "type": "string",
                "enum": ["next", "first", "last", "fastest", "arrival", "count", "airlines"],
                "description": (
                    "ONLY when the line ASKS something about the flights rather "
                    "than asking to see them. next: when is the next flight. "
                    "first: the first flight of the day. last: the last flight. "
                    "fastest: which is the fastest or quickest. arrival: when is "
                    "the earliest I can be there. count: how many flights, are "
                    "there any, is there a flight. airlines: which airlines fly. "
                    "Omit for 'show me flights', 'flights to X', 'fastest way "
                    "to X' -- those are requests, not questions."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "0 to 1: how sure you are that this sentence asks for flights between places.",
            },
        },
        "required": ["destination", "confidence"],
    },
}

INTENT_FLIGHT_TOOL = {
    "name": "lookup_flight",
    "description": (
        "The user names ONE specific flight and wants to know about it: its "
        "status, times, gate, terminal, whether it is on time, delayed, landed. "
        "Call this whenever a flight number appears in any form -- '6E5071', "
        "'6e 5071', '6E-5071', 'AI 2630', 'indigo 5071', 'is SK936 on time', "
        "'when does EK500 land'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "flight_number": {
                "type": "string",
                "description": (
                    "IATA form, no spaces: two-character airline code then the "
                    "digits, e.g. 6E5071, AI2630, SK936. Convert airline names to "
                    "codes: IndiGo 6E, Air India AI, Akasa QP, SpiceJet SG, "
                    "Vistara UK, Air India Express IX, Emirates EK, Qatar QR, "
                    "Etihad EY, KLM KL, Lufthansa LH, British Airways BA, SAS SK, "
                    "Singapore SQ."
                ),
            },
            "date": {
                "type": "string",
                "description": "YYYY-MM-DD, only if the sentence names a day. Otherwise omit.",
            },
        },
        "required": ["flight_number"],
    },
}

# THE GMAIL TOOL STAYS AND THE OTHER TWO DO NOT. get_flight_status and
# check_my_flight both ran a flight lookup on the SERVER, undated and without an
# origin; lookup_flight above hands the same question to the device, which runs
# it on the flight's own date and origin and guards the storage write. Keeping
# both would give the model two tools for one question and let it pick the
# worse one. find_flight_from_gmail has no device equivalent -- the mailbox is
# read here -- so it stays.
INTENT_TOOLS = [INTENT_ROUTE_TOOL, INTENT_FLIGHT_TOOL, TOOLS[2]]

INTENT_SYSTEM = (
    "You are the command line of a flight-tracking app. The user typed ONE line. "
    "Today is {today}. Work out what they want and act:\n"
    "\n"
    "FLIGHTS BETWEEN PLACES -> call search_route. Any phrasing, any language, "
    "any script: 'delhi to indore flights', 'flights delhi indore', 'dilli se "
    "indore ki flight', 'vuelos de madrid a barcelona', 'vol paris nice', "
    "'flüge von münchen nach berlin', 'voli roma milano', 'voos são paulo rio', "
    "'lot warszawa kraków', 'москва питер', 'istanbul'dan ankara'ya', 'رحلات "
    "من دبي إلى القاهرة', 'تهران به مشهد', '東京から大阪', '北京到上海', '서울에서 "
    "부산', 'กรุงเทพไปเชียงใหม่', 'penerbangan jakarta ke bali', 'IDR DEL', "
    "'lax-jfk', 'yyz to yvr', 'flights to bombay' (destination only).\n"
    "\n"
    "RETURN PLACE NAMES IN ENGLISH, spelling corrected, under the CURRENT name: "
    "Bombay/Bambai/मुंबई->Mumbai, Dilli/दिल्ली->Delhi, Madras->Chennai, "
    "Calcutta->Kolkata, Bangalore->Bengaluru, Peking->Beijing, "
    "Canton->Guangzhou, Saigon->Ho Chi Minh City, Rangoon->Yangon, "
    "Leningrad->St Petersburg, Constantinople->Istanbul, München->Munich, "
    "Wien->Vienna, Praha->Prague, Warszawa->Warsaw, Moskva/Москва->Moscow, "
    "Roma->Rome, Milano->Milan, Lisboa->Lisbon, Genève->Geneva, "
    "Bruxelles->Brussels, København->Copenhagen, Athina->Athens, Krung "
    "Thep/กรุงเทพ->Bangkok, 東京->Tokyo, 北京->Beijing, 上海->Shanghai, "
    "서울->Seoul, القاهرة->Cairo, دبي->Dubai, الرياض->Riyadh, تهران->Tehran, "
    "Kaapstad->Cape Town, Joburg/Jozi->Johannesburg, Sampa->São Paulo, "
    "Baires/BsAs->Buenos Aires, CDMX->Mexico City, NYC->New York, LA->Los "
    "Angeles, SF->San Francisco, DC->Washington, Vegas->Las Vegas, "
    "Philly->Philadelphia, KL->Kuala Lumpur, HK->Hong Kong. If the user typed "
    "a 3-letter airport code, return the code.\n"
    "\n"
    "A CITY WITH SEVERAL AIRPORTS -- London, New York, Paris, Tokyo, Moscow, "
    "Milan, Washington, Buenos Aires, São Paulo, Shanghai, Seoul, Bangkok, "
    "Istanbul, Goa -- is returned as the CITY; the app offers the choice. But "
    "when the user names the AIRPORT -- Heathrow, Gatwick, JFK, Newark, Orly, "
    "Haneda, Narita, Sheremetyevo, Domodedovo, Linate, Malpensa, Dulles, "
    "Ezeiza, Congonhas, Guarulhos, Hongqiao, Gimpo, Don Mueang, Sabiha Gökçen "
    "-- return that airport's name, not the city's.\n"
    "\n"
    "THE SAME NAME IN MORE THAN ONE COUNTRY -- Portland, San José, Santiago, "
    "Valencia, Hyderabad, Birmingham, Victoria, Springfield -- is told apart by "
    "origin_country / destination_country, in English, and ONLY when the "
    "sentence settles it: the country is named, or the other end makes one "
    "reading plain ('delhi to hyderabad' -> India; 'lima to santiago' -> Chile, "
    "the capital next door, not Cuba). Otherwise leave the country out. Never "
    "guess it.\n"
    "\n"
    "If the sentence does not say where the flight LEAVES FROM, omit origin -- "
    "never guess one.\n"
    "\n"
    "DATES resolve against today: tomorrow, day after tomorrow, this friday, "
    "next monday, 'the 24th' (the next 24th), '24 sep', '3/10' (day/month). "
    "A RANGE -- this weekend, next week, early October -- is the FIRST day of "
    "the range with date_kind 'range' and range_label in the user's words. "
    "Time of day: morning, afternoon, evening; red-eye, late night and early "
    "morning are 'overnight'. Ordering: fastest/quickest/shortest -> fastest; "
    "earliest/first/soonest/next -> earliest. 'Cheapest' is not something this "
    "app knows; ignore it and search anyway. ALL OF THIS IN ANY LANGUAGE: "
    "mañana, demain, morgen, domani, amanhã, jutro, завтра, yarın, 明日, 내일, "
    "غدا, فردا, พรุ่งนี้, besok are tomorrow; hoy, aujourd'hui, heute, oggi, "
    "hoje, сегодня, bugün, 今日, 오늘, اليوم, วันนี้, hari ini are today; "
    "stasera, ce soir, heute abend, esta noche, hoje à noite, сегодня вечером, "
    "bu akşam, 今晩, 오늘 밤, الليلة are tonight; weekday and month names "
    "likewise; por la mañana, le matin, morgens, di mattina, de manhã, cedo, "
    "утром, sabah, 朝, 아침, صباحا are morning, and the afternoon, evening and "
    "night words likewise.\n"
    "\n"
    "A QUESTION ABOUT THE FLIGHTS is still search_route, with question set: "
    "'when is the next flight to X' -> next; 'what is the first flight tomorrow' "
    "-> first; 'when is the last flight' -> last; 'which is the fastest' -> "
    "fastest; 'when is the earliest I can be in X' -> arrival; 'how many "
    "flights', 'are there any flights', 'is there a flight' -> count; 'which "
    "airlines fly' -> airlines. Set question ONLY when the line asks -- it "
    "starts with when, what, which, how many, is there, are there, or ends in "
    "a question mark. 'Show me the fastest flight' and 'fastest way to X' are "
    "requests: set sort, leave question unset.\n"
    "\n"
    "ONE SPECIFIC FLIGHT -> call lookup_flight, whenever a flight number appears "
    "in any form, including inside a question ('is 6E5071 on time', 'what gate "
    "is EK500', 'when does SK936 land', 'track ai2630', 'indigo 5071').\n"
    "\n"
    "THE USER'S OWN FLIGHT WITH NO NUMBER ('is my flight on time', 'what is my "
    "gate', 'when does my plane land') -> call find_flight_from_gmail.\n"
    "\n"
    "ANYTHING ELSE -> answer in plain text, briefly. If you could not read the "
    "line as any of the above, say in one short line what was missing and give "
    "an example that would work. Never invent flight data.\n"
    "\n"
    "Text answers are plain terminal output: no emojis, no markdown, no bold, "
    "no headers, no tables, each fact on its own line, lowercase labels with a "
    "colon. Reproduce every timezone label and '(predicted)' qualifier exactly "
    "as a tool returns it."
)

_FLIGHT_NUMBER_RE = re.compile(r"^([A-Z0-9]{2})(\d{1,4})([A-Z]?)$")


def _device_today(raw):
    """The device's date if it sent a well-formed one, else the server's UTC date."""
    text = str(raw or "").strip()
    if _ISO_DAY_RE.match(text):
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


def _intent_str(raw, key):
    v = raw.get(key)
    v = str(v).strip() if isinstance(v, str) else ""
    return v or None


def _intent_route(raw: dict, today) -> tuple[dict | None, str | None]:
    """(intent, error). The model's fields, re-checked before they leave.

    NOTHING IS TRUSTED, for /parse's reason: the enums are re-tested and the
    date is re-parsed and re-bounded here, and the device resolves the names
    itself. A DATE THAT FAILS IS KEPT AS AN ERROR RATHER THAN DROPPED: /parse
    silently nulled a bad date and searched today, which answers a different
    question for four units. The device reads date_error and says so instead.
    """
    destination = _intent_str(raw, "destination")
    if destination is None:
        return None, INTENT_NO_DESTINATION
    band = _intent_str(raw, "band")
    if band not in ("morning", "afternoon", "evening", "overnight"):
        band = None
    sort = _intent_str(raw, "sort")
    if sort not in ("fastest", "earliest"):
        sort = None
    kind = _intent_str(raw, "date_kind")
    if kind not in ("single", "range"):
        kind = None
    question = _intent_str(raw, "question")
    if question not in INTENT_QUESTIONS:
        question = None
    date = _intent_str(raw, "date")
    date_error = None
    if date is not None:
        day, err = _validate_route_date(date)
        if err is not None:
            date, date_error = None, err
        else:
            date = day
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence", 1.0))))
    except (TypeError, ValueError):
        conf = 1.0
    return {
        "kind": "route",
        "origin": _intent_str(raw, "origin"),
        "destination": destination,
        # A hint for ORDERING the device's options, never for choosing one. See
        # the prompt: set only when the sentence settles a name that exists in
        # more than one country.
        "origin_country": _intent_str(raw, "origin_country"),
        "destination_country": _intent_str(raw, "destination_country"),
        "date": date,
        "date_kind": kind if date is not None or kind == "range" else None,
        "range_label": _intent_str(raw, "range_label") if kind == "range" else None,
        "band": band,
        "sort": sort,
        "question": question,
        "date_error": date_error,
        "confidence": conf,
    }, None


def _intent_flight(raw: dict) -> tuple[dict | None, str | None]:
    """(intent, error). The number normalised, or a reason it could not be."""
    number = re.sub(r"[\s\-.]", "", str(raw.get("flight_number") or "")).upper()
    m = _FLIGHT_NUMBER_RE.match(number)
    # A CARRIER CODE HAS A LETTER IN IT. "12345" is not a flight and "6E5071" is;
    # the digits-only prefix is the one shape the regex above cannot refuse.
    if not m or not re.search(r"[A-Z]", m.group(1)):
        return None, INTENT_BAD_NUMBER
    date = _intent_str(raw, "date")
    date_error = None
    if date is not None:
        day, err = _validate_route_date(date, max_future=FLIGHT_MAX_FUTURE_DAYS)
        if err is not None:
            date, date_error = None, err
        else:
            date = day
    return {"kind": "flight", "flight_number": number, "date": date, "date_error": date_error}, None


def _intent_reply(intent=None, response=None, flight=None, error=None):
    return {"intent": intent, "response": response, "flight": flight, "error": error}


def _intent_from_calls(calls, today):
    """The first intent among a turn's calls, as (intent, error), or None."""
    for call in calls:
        if call.name == "search_route":
            return _intent_route(call.args or {}, today)
        if call.name == "lookup_flight":
            return _intent_flight(call.args or {})
    return None


@app.post("/intent")
def intent(req: IntentRequest, request: Request):
    text = str(req.message or "").strip()
    if not text:
        return _intent_reply(response=INTENT_EMPTY)
    today = _device_today(req.today)
    gmail_access, _gmail_code = _gmail_access(request, req.gmail_token)
    system = INTENT_SYSTEM.format(today=today.isoformat())
    messages = [llm.user_text(text)]
    captured_flight = None

    for _round in range(CHAT_MAX_TOOL_ROUNDS):
        try:
            turn = llm.generate(model=llm.CHAT_MODEL, system=system, messages=messages,
                                tools=INTENT_TOOLS, max_tokens=CHAT_MAX_TOKENS)
        except Exception as exc:  # noqa: BLE001
            return _intent_reply(error=_chat_error(exc), flight=captured_flight)

        # AN INTENT ENDS THE CALL. It is returned, not run: the board and the
        # flight lookup happen on the device, on its own dataset and its own
        # date, through the code the free rungs use.
        found = _intent_from_calls(turn.tool_calls, today)
        if found is not None:
            intent_, err = found
            if intent_ is not None:
                return _intent_reply(intent=intent_, flight=captured_flight)
            return _intent_reply(response=err, flight=captured_flight)

        if turn.tool_calls:
            # The Gmail tool, run here as /chat runs it, and the answer next round.
            results = []
            for call in turn.tool_calls:
                result_text, flight_data = run_tool(call.name, call.args, gmail_access)
                if flight_data is not None:
                    captured_flight = flight_data
                results.append((call, result_text))
            messages.append(llm.model_turn(turn))
            messages.append(llm.tool_results(results))
            continue

        # PROSE IS THE ANSWER. See the note on the retired retry above.
        if turn.text:
            return _intent_reply(response=turn.text, flight=captured_flight)
        return _intent_reply(error=CHAT_ERROR_GENERIC, flight=captured_flight)

    return _intent_reply(error=CHAT_ERROR_TOO_MANY_STEPS, flight=captured_flight)


# ──────────────────────────────────────────────
# ALERTS: WEBHOOK, READ-BACK, AND WATCH REGISTRATION
# ──────────────────────────────────────────────
#
# TWO SECRETS, NOT ONE. The webhook secret is given to the provider and lives in
# a URL they hold; the read secret is only ever used by us. Rotating either one
# must not break the other, and they have completely different exposure — the
# webhook one is in somebody else's configuration.
#
# Both are Cloud Run environment variables and neither is ever written to a file
# in this repository.
ALERT_WEBHOOK_SECRET = os.getenv("ALERT_WEBHOOK_SECRET")
ALERT_READ_SECRET = os.getenv("ALERT_READ_SECRET")

# THE THIRD SECRET, AND IT TRAVELS DIFFERENTLY FROM THE OTHER TWO.
#
# IN A HEADER, NOT THE PATH, AND THAT IS THE WHOLE REASON THIS IS NOT SPELLED
# LIKE /alerts. Cloud Run writes the full request path into its access logs on
# every single call, so a secret in the path is a secret copied into Cloud
# Logging in plaintext, permanently, at whatever retention the project has.
# /alerts has no choice -- the alert provider's dashboard accepts a URL and
# nothing else -- and that is a constraint being tolerated there, not a pattern
# worth repeating. These two are called by our own app, which can send a header.
#
# IT IS ALSO WEAKER THAN THE OTHER TWO, and being plain about that is the point:
# this one is COMPILED INTO A SHIPPED MOBILE APP. Anyone who unpacks the binary
# has it. It stops a stranger who merely knows the URL and nothing more.
WATCH_SECRET = os.getenv("WATCH_SECRET")

# The header the two watch endpoints read it from. Named here rather than
# spelled twice: FastAPI derives "x-watch-secret" from the parameter name, and
# this constant is what the log lines and any future caller refer to.
WATCH_SECRET_HEADER = "X-Watch-Secret"

# At most this much body in the log line. The log is a backstop, not a copy of
# the payload — the bucket holds the payload — and one large delivery must not
# push everything else out of a log view.
ALERT_LOG_PREVIEW_CHARS = 500

# Fixed strings, as everywhere else in this file: the client learns that
# something did not work, the log learns what.
WATCH_ERROR = "Could not register this flight for alerts."
UNWATCH_ERROR = "Could not deregister this flight."
ALERT_READ_ERROR = "Could not read deliveries."


def _secret_ok(supplied: str, expected) -> bool:
    """Constant-time comparison, and an unset secret matches nothing.

    compare_digest rather than ==, so the comparison does not leak the length of
    a correct prefix through how long it takes to fail.
    """
    if not expected:
        return False
    return secrets.compare_digest(str(supplied), str(expected))


def _alert_not_found() -> JSONResponse:
    """404, not 403.

    A 403 confirms the route exists and only the secret was wrong, which tells
    anyone probing that they have found something worth probing. A 404 says
    nothing at all, and a URL whose secret is wrong is, for our purposes, a URL
    that does not exist.
    """
    return JSONResponse(status_code=404, content={"error": "not found"})


@app.post("/alerts/{secret}")
async def alerts_webhook(secret: str, request: Request):
    if not _secret_ok(secret, ALERT_WEBHOOK_SECRET):
        # The supplied value is NEVER logged. A rejected secret in a log is a
        # secret in a log, and near-misses are exactly what an attacker wants
        # read back to them.
        logger.warning("alert webhook rejected: secret mismatch or unset")
        return _alert_not_found()

    # PAST THE SECRET CHECK THIS ALWAYS RETURNS 200, AND THAT IS NOT NEGOTIABLE.
    #
    # The provider bills on SEND, not on delivery, and its delivery retries
    # default to zero. A non-2XX therefore loses the alert AND the credit is
    # already spent — there is no retry to fix it and nothing to recover. So an
    # unparseable body, an oversized body, a failed bucket write and an
    # unexpected exception all still return 200, and the log line below is what
    # tells us something went wrong.
    body = await request.body()
    try:
        delivery = store.build_delivery(body, {
            # Only these three. Never the full header set, and never any part of
            # the URL path — the path is where the secret is.
            "content-type": request.headers.get("content-type"),
            "user-agent": request.headers.get("user-agent"),
            "content-length": request.headers.get("content-length"),
        })

        # LOG FIRST, WRITE SECOND, AND DO NOT REORDER THIS.
        #
        # The log line is the backstop: a slow or failing bucket write still
        # leaves a counted delivery in Cloud Logging, with enough of the payload
        # to know what arrived. Writing first and logging after would mean a
        # bucket outage loses the delivery entirely.
        #
        # logger.WARNING rather than info, deliberately. This logger has no
        # handler configuration, so its effective level is the root logger's
        # WARNING and an info() call would be dropped silently — the line would
        # simply never appear, which is the one failure this line exists to
        # prevent.
        logger.warning(
            "ALERTDELIVERY id=%s at=%s bytes=%s truncated=%s parsed=%s items=%s credits=%s preview=%r",
            delivery["delivery_id"],
            delivery["received_at"],
            delivery["body_bytes"],
            delivery["truncated"],
            delivery["parsed_json"],
            delivery["item_count"],
            delivery["credits_remaining"],
            delivery["raw_body"][:ALERT_LOG_PREVIEW_CHARS],
        )

        # INLINE, never a BackgroundTask. Cloud Run throttles CPU once the
        # response is returned unless CPU-always-on is set, so post-response
        # work is not reliably scheduled and a background write can simply not
        # happen.
        result = store.record_delivery(delivery)
        if not result.get("ok"):
            logger.warning(
                "ALERTDELIVERY store failed id=%s error=%s",
                delivery["delivery_id"], result.get("error"),
            )
    except Exception as exc:
        # Still 200. See above.
        logger.warning("ALERTDELIVERY handler failed: %s", type(exc).__name__)

    return {"ok": True}


@app.get("/alerts/{secret}/deliveries")
def alerts_list(secret: str, day: str | None = None, limit: int = store.DEFAULT_LIST_LIMIT):
    if not _secret_ok(secret, ALERT_READ_SECRET):
        logger.warning("alert read rejected: secret mismatch or unset")
        return _alert_not_found()
    result = store.list_deliveries(day, limit)
    if not result.get("ok"):
        logger.warning("alert list failed: %s", result.get("error"))
        return {"error": ALERT_READ_ERROR}
    # Summaries only. A day of raw bodies is megabytes and none of it is needed
    # to decide which delivery is worth opening.
    return {
        "day": result["day"],
        "count": result["count"],
        "deliveries": result["deliveries"],
    }


@app.get("/alerts/{secret}/deliveries/{delivery_id}")
def alerts_get(secret: str, delivery_id: str, day: str | None = None):
    if not _secret_ok(secret, ALERT_READ_SECRET):
        logger.warning("alert read rejected: secret mismatch or unset")
        return _alert_not_found()
    result = store.get_delivery(delivery_id, day)
    if not result.get("ok"):
        logger.warning("alert get failed: %s", result.get("error"))
        return {"error": ALERT_READ_ERROR}
    return result["delivery"]


class WatchRequest(BaseModel):
    device_id: str
    push_token: str | None = None
    platform: str | None = None
    flight_number: str
    flight_date: str
    # True: the person is on the flight. False: they are meeting it. Absent:
    # an app that predates the flag, read as on it. See notify.subject.
    owned: bool | None = None


class UnwatchRequest(BaseModel):
    device_id: str
    flight_number: str
    flight_date: str


# THE GAP IS NARROWED, NOT CLOSED, AND THE DIFFERENCE IS THE WHOLE NOTE.
#
# WHAT CHANGED: these two took nothing at all, so anyone who knew the URL could
# register or remove a watch for any device id they could guess. They now
# require a shared secret in the X-Watch-Secret header, compared with the same
# _secret_ok the three /alerts endpoints use and failing to the same 404.
#
# WHAT DID NOT CHANGE: the secret ships inside a public mobile app. Anyone who
# unpacks the binary has it, and can then still write to any device id they can
# guess — and a device id is a v4 UUID, so guessing one remains the hard part
# rather than the impossible part. The validation and the two caps in store.py
# are still doing the real work.
#
# SO THE BAR THIS CLEARS IS "not writable by a stranger with the URL", which is
# worth having and is not the same thing as authenticated. What would actually
# close it is proof that the caller owns the device id it is writing: a
# per-device token issued on first launch and required thereafter. That is a
# different change and this is not it.
#
# THE 404 IS NOT DECORATION EITHER. A 403 would confirm that the route exists
# and only the secret was wrong, which is exactly what somebody probing wants
# read back to them. See _alert_not_found, whose name is now slightly wrong for
# one of its callers and which is reused anyway, because the alternative is
# renaming a function three untouched endpoints depend on.
@app.post("/watch")
def watch(req: WatchRequest, x_watch_secret: str | None = Header(default=None)):
    # DEFAULT None RATHER THAN REQUIRED. A required header FastAPI cannot find
    # is a 422 with a validation body naming the header, which both tells a
    # prober what to send and is not the 404 this endpoint promises.
    if not _secret_ok(x_watch_secret, WATCH_SECRET):
        # The supplied value is NEVER logged. A rejected secret in a log is a
        # secret in a log, and near-misses are what an attacker wants back.
        logger.warning("watch rejected: bad or missing %s", WATCH_SECRET_HEADER)
        return _alert_not_found()
    result = store.register_watch(
        req.device_id, req.push_token, req.platform, req.flight_number, req.flight_date,
        owned=req.owned,
    )
    if not result.get("ok"):
        # The distinct reason — which cap, which field — goes to the log. The
        # client gets a fixed string, as with every other error in this file.
        logger.warning("watch rejected: %s", result.get("error"))
        return {"error": WATCH_ERROR}
    return {"ok": True, "created": result.get("created")}


# ── WHAT THE SERVER FOUND WHEN THIS FLIGHT WAS CANCELLED ───────────────────
#
# THE DEVICE DOES NO SEARCHING. The poller has already walked the board, judged
# every row against the next leg and stored the result; this hands that back.
# NO PROVIDER CALL HAPPENS HERE, on any path, which is what lets the drawer open
# instantly and what keeps a screen nobody scrolls from costing units.
#
# ── AND NOTHING IS CACHED ON THE DEVICE ────────────────────────────────────
#
# These rows are provider data under a seven-day ceiling -- see
# docs/connection-search.md -- and the app's own store is the open question in
# that same document: a SavedFlight DTO is written to AsyncStorage and never
# deleted by age. Copying board rows onto the device would extend an unresolved
# exposure to a second class of data, deliberately, while the first is still
# unanswered. Server-side they expire with the state object, at five days.
#
# ── WHY THE OWNERSHIP CHECK IS NOT DECORATION ──────────────────────────────
#
# X-Watch-Secret IS A SHARED CLIENT SECRET. It ships inside the app bundle as
# EXPO_PUBLIC_WATCH_SECRET, so it establishes "a build of this app is calling"
# and nothing whatever about WHO. That is adequate for /watch, which only lets a
# caller subscribe a token it already holds. It is not adequate on its own here,
# where the response is somebody's itinerary.
#
# SO THE DEVICE ID IS THE SECOND FACTOR, such as it is, and the honest reading
# is that this is enumeration-resistant rather than secure: a device id is a
# random opaque value rather than a guessable one, and a caller who has both a
# bundle and a device id can read that device's alternatives. Worth revisiting
# when there is an account token to carry instead.
#
# ── NOT OWNED AND NOT FOUND ANSWER IDENTICALLY ─────────────────────────────
#
# Both return an empty block rather than a distinguishable refusal, so a caller
# cannot use this to learn which flights a device is watching. The drawer needs
# no distinction: with nothing stored it says the search is still running, which
# is the true thing to say in both cases.
@app.get("/alternatives/{flight_number}")
def get_alternatives(flight_number: str, date: str | None = None,
                     device_id: str | None = None,
                     x_watch_secret: str | None = Header(default=None)):
    if not _secret_ok(x_watch_secret, WATCH_SECRET):
        logger.warning("alternatives rejected: bad or missing %s", WATCH_SECRET_HEADER)
        return _alert_not_found()
    num = str(flight_number or "").strip().upper()
    day = str(date or "").strip()
    # THE FORMAT ONLY, NOT THE HORIZON. _validate_route_date refuses past dates
    # because a route SEARCH cannot answer for them; this reads an object that
    # is already on disk, and a flight cancelled yesterday is exactly the case
    # somebody opens the drawer for.
    if not num or not _ISO_DAY_RE.match(day):
        return {"alternatives": None}
    # NOT OWNED, NOT WATCHED, OR THE WATCH STORE COULD NOT BE READ -- owns_watch
    # collapses all three into no, deliberately. Logged here rather than there
    # because this is where the request is; the number and the date are already
    # in this log line's siblings and neither is a secret.
    if not store.owns_watch(device_id, num, day):
        return {"alternatives": None}
    try:
        doc, _gen = pollstate.read_state(num, day)
    except Exception:  # noqa: BLE001
        # UNREADABLE STATE IS AN EMPTY ANSWER, NOT AN ERROR. The drawer's
        # fallback -- "still looking" -- is the right thing to show while the
        # bucket is unavailable, and a 500 here would make a transient storage
        # blip look like a broken feature.
        logger.warning("alternatives: state unreadable for %s/%s", num, day)
        return {"alternatives": None}
    return {"alternatives": (doc or {}).get("alternatives")}


# ── WHAT THE POLLER ALREADY KNOWS ABOUT A DEVICE'S OWN FLIGHTS ─────────────
#
# THE SERVER HAS BEEN POLLING THE WHOLE TIME, and the device never read it. The
# poller stores exactly the DTO /flight returns -- both come from
# fetch_flight_full -- and until now the only way a screen saw it was a
# pull-to-refresh that asked the provider again and paid for it. This hands the
# stored copy back, so an open app can stay current once a minute for nothing.
#
# NO PROVIDER CALL ON ANY PATH, which is the whole of the feature and is
# asserted in test_watched.py by replacing every provider with something that
# raises. The cost is a Cloud Run request and a storage read per flight.
#
# ONE REQUEST FOR EVERY LIVE FLIGHT, repeated `f=NUMBER:DATE`, so a device with
# four legs in the air window makes one call a minute rather than four. The
# watch store is read once for all of them -- see store.watched_by_device.
#
# ── AUTHENTICATED AS /alternatives IS, WITH ONE DIFFERENCE ─────────────────
#
# THE SECRET AND THE DEVICE ID, and the same honest limit: this is
# enumeration-resistant rather than secure. See the note on /alternatives.
#
# MEETERS INCLUDED. /alternatives returns owned flights only, because rebooking
# options are a passenger's. A flight's status is exactly what somebody at
# arrivals is watching for, and the device already holds the record.
#
# A PAIR THE DEVICE DOES NOT WATCH IS OMITTED, NOT REFUSED, for the same reason
# not-owned and not-found answer alike there: a distinguishable refusal would
# tell a caller which flights a device watches.
#
# ── AND THE AGE IS CORRECTED, OR EVERY READ WOULD LIE ──────────────────────
#
# THE STORED DTO SAYS data_age_seconds 0, because it was fresh when the poller
# fetched it. The device turns that into updatedAt = now - age, and updatedAt
# gates whether a live countdown is trusted -- see COUNTDOWN_MAX_AGE_MS in
# lib/flightstatus.tsx. Served as stored, a copy fetched fourteen minutes ago
# would arrive claiming to be brand new, and would claim it again every minute.
# So the time since the poll is added before it leaves: the device's own
# arithmetic then lands on the provider's time, unchanged and correct.
WATCHED_MAX_FLIGHTS = 12


def _aged_dto(dto, polled_at, now):
    """The stored DTO with data_age_seconds made true as of now, or None."""
    if not isinstance(dto, dict):
        return None
    out = dict(dto)
    try:
        polled = datetime.fromisoformat(str(polled_at).replace("Z", "+00:00"))
        if polled.tzinfo is None:
            polled = polled.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return out
    since = max(0, int((now - polled).total_seconds()))
    base = dto.get("data_age_seconds")
    out["data_age_seconds"] = (base if isinstance(base, (int, float)) else 0) + since
    return out


@app.get("/watched")
def get_watched(device_id: str | None = None,
                f: list[str] = Query(default=[]),
                x_watch_secret: str | None = Header(default=None)):
    if not _secret_ok(x_watch_secret, WATCH_SECRET):
        logger.warning("watched rejected: bad or missing %s", WATCH_SECRET_HEADER)
        return _alert_not_found()
    wanted = []
    for item in (f or [])[:WATCHED_MAX_FLIGHTS]:
        num, _, day = str(item or "").partition(":")
        num, day = num.strip().upper(), day.strip()
        if num and _ISO_DAY_RE.match(day):
            wanted.append((num, day))
    if not wanted:
        return {"flights": []}
    mine = store.watched_by_device(device_id)
    now = datetime.now(timezone.utc)
    out = []
    for num, day in wanted:
        if (num, day) not in mine:
            continue
        try:
            doc, _gen = pollstate.read_state(num, day)
        except Exception:  # noqa: BLE001
            # ONE UNREADABLE FLIGHT IS ONE OMITTED FLIGHT. The device keeps what
            # it has for that one and updates the rest.
            logger.warning("watched: state unreadable for %s/%s", num, day)
            continue
        if not doc or not doc.get("dto"):
            continue
        out.append({
            "flight_number": num,
            "flight_date": day,
            "dto": _aged_dto(doc.get("dto"), doc.get("last_adb_at"), now),
            # WHEN THE SERVER LAST ASKED THE PROVIDER, which is not when this was
            # read. The device needs both apart: this one to refuse a stored copy
            # older than a manual refresh it already holds.
            "polled_at": doc.get("last_adb_at"),
            # THE LANDING TOO, so the device need not ask FR24 itself for a
            # flight the server is already watching. See saved.tsx's sweep.
            "landing": doc.get("landing"),
            "landing_checked_at": doc.get("last_fr24_at"),
        })
    return {"flights": out}


# The same secret, the same 404, and the same narrowed gap as /watch above.
@app.post("/unwatch")
def unwatch(req: UnwatchRequest, x_watch_secret: str | None = Header(default=None)):
    if not _secret_ok(x_watch_secret, WATCH_SECRET):
        logger.warning("unwatch rejected: bad or missing %s", WATCH_SECRET_HEADER)
        return _alert_not_found()
    result = store.unregister_watch(req.device_id, req.flight_number, req.flight_date)
    if not result.get("ok"):
        logger.warning("unwatch rejected: %s", result.get("error"))
        return {"error": UNWATCH_ERROR}
    # Removing nothing is a success: unsave is fire-and-forget on the device, so
    # a retry must be indistinguishable from a first attempt.
    return {"ok": True, "removed": result.get("removed")}


# ──────────────────────────────────────────────
# THE POLLER
# ──────────────────────────────────────────────
#
# Cloud Scheduler pokes this every two minutes. It does not decide anything --
# poller.run_once() does -- and it sends nothing to anybody. See poller.py.
#
# ITS OWN SECRET, NOT WATCH_SECRET. WATCH_SECRET is compiled into a shipped
# mobile app and anyone who unpacks the binary has it; that is an acceptable
# gate on "register this flight" and an unacceptable one on "spend units now".
# A stranger with the app's secret could otherwise poke this in a loop and empty
# the month's allowance.
POLL_SECRET = os.getenv("POLL_SECRET")
POLL_SECRET_HEADER = "X-Poll-Secret"

# ONE POLL AT A TIME, AND THE LOCK IS IN THE BUCKET rather than in this process,
# because Cloud Run may be running several. Two overlapping passes would each
# read the same state, each decide the same flights were due, and each pay for
# them.
POLL_LOCK_KEY = "runtime/poll.lock"
POLL_LOCK_TTL_SECONDS = 300


@app.post("/poll")
def poll(x_poll_secret: str | None = Header(default=None)):
    # Default None rather than required, and a 404 rather than a 403, for the
    # reasons spelled out at _alert_not_found and /watch above.
    if not _secret_ok(x_poll_secret, POLL_SECRET):
        logger.warning("poll rejected: bad or missing %s", POLL_SECRET_HEADER)
        return _alert_not_found()

    lock = pollstate.take_lock(POLL_LOCK_KEY, POLL_LOCK_TTL_SECONDS)
    if not lock:
        # NOT AN ERROR. A poke arriving while the previous one is still working
        # is the system behaving exactly as intended under a slow provider, and
        # a 500 here would have Cloud Scheduler retry it -- which is the one
        # thing that must not happen.
        logger.info("poll skipped: another pass is already running")
        return {"ok": True, "skipped": "already running"}

    try:
        return poller.run_once()
    except Exception:
        # The client gets a fixed string, as everywhere else in this file. The
        # traceback goes to the log.
        logger.exception("poll failed")
        return JSONResponse(status_code=500, content={"error": "Poll failed."})
    finally:
        pollstate.release_lock(POLL_LOCK_KEY)


# ──────────────────────────────────────────────
# DISPATCH
# ──────────────────────────────────────────────
# THE OTHER HALF OF /poll. The poll decides what to say and leaves it in each
# flight's outbox; this takes it out and sends it. They are separate endpoints
# on separate schedules because notify defers a cancellation through the night:
# a message written at 02:00 to be delivered at 07:00 needs a pass at 07:00,
# and the poll of that particular flight may not come round then. See the note
# at the top of dispatch.py.
#
# ITS OWN SECRET. /poll and /dispatch are woken by the same Cloud Scheduler and
# neither is reachable by anything else, so sharing one would have been
# defensible -- but they are separate env vars on the service, so one can be
# rotated without silencing the other, and a scheduler job misconfigured against
# the wrong endpoint fails closed rather than running the wrong pass.
#
# UNSET MATCHES NOTHING. _secret_ok returns False for an empty expected value,
# so a deployment that forgets DISPATCH_SECRET has a closed endpoint rather than
# an open one. There is deliberately no fallback to POLL_SECRET: a fallback
# would mean the endpoint quietly stayed reachable under a secret its own
# scheduler is not sending.
DISPATCH_SECRET = os.getenv("DISPATCH_SECRET")
DISPATCH_SECRET_HEADER = "X-Dispatch-Secret"

DISPATCH_LOCK_KEY = "runtime/dispatch.lock"
DISPATCH_LOCK_TTL_SECONDS = 300


@app.post("/dispatch")
def dispatch_pass(x_dispatch_secret: str | None = Header(default=None)):
    # 404 rather than 403, as at /poll and /watch above.
    if not _secret_ok(x_dispatch_secret, DISPATCH_SECRET):
        logger.warning("dispatch rejected: bad or missing %s", DISPATCH_SECRET_HEADER)
        return _alert_not_found()

    lock = pollstate.take_lock(DISPATCH_LOCK_KEY, DISPATCH_LOCK_TTL_SECONDS)
    if not lock:
        # NOT AN ERROR, for the reason /poll gives: a 500 would have Cloud
        # Scheduler retry, and two overlapping passes are exactly what the lock
        # exists to prevent. The claim-before-send in dispatch.py would stop a
        # duplicate anyway; this stops the wasted work as well.
        logger.info("dispatch skipped: another pass is already running")
        return {"ok": True, "skipped": "already running"}

    try:
        return dispatch.run_once()
    except Exception:
        logger.exception("dispatch failed")
        return JSONResponse(status_code=500, content={"error": "Dispatch failed."})
    finally:
        pollstate.release_lock(DISPATCH_LOCK_KEY)
