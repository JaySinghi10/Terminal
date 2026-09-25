"""A flight's own history, kept long enough to review after the trip.

── WHY THIS EXISTS ─────────────────────────────────────────────────────────────

Everything the server knows about a flight lives in its poll state, and poll
state is deleted twenty-six hours after the flight is done and swept at five
days regardless. That is right for state -- it is provider data, and nothing
reads a five-day-old poll -- and it means that by the time anybody sits down to
ask "why did she get that push twenty minutes late", the record that would say
is gone.

So for the flights named in DIAG_FLIGHTS, every poll and every notification
decision is copied out as it happens, into an object of its own that outlives
the state it came from.

── WHAT IS KEPT, AND THE LINE THE LICENCE DRAWS THROUGH IT ─────────────────────

AeroDataBox has ruled that its data stays Contents however it is reshaped -- see
docs/connection-search.md §1 -- and Contents may not be held past seven days. A
gate number copied into a log is still their gate number. So every event here is
split in two:

  THE SKELETON is this server's own record of its own actions: when it polled,
  in which tier, which providers it asked, which FIELD NAMES changed, which
  notifications it decided, sent, had delivered or dropped, and why. None of
  that is a provider value, and it is kept for DIAG_KEEP_DAYS.

  THE VALUES are what the provider said -- the gate before and after, the
  status, the rendered text of a push. They are kept for DIAG_VALUES_DAYS, one
  short of the seven-day ceiling for the same margin pollstate keeps, and then
  stripped from the event while the skeleton stays.

So a review within six days of a flight sees everything; a review after sees
exactly what happened and when, without the numbers it happened to.

THE SKELETON'S STANDING HAS NOT BEEN PUT TO AeroDataBox. "The gate changed at
10:42" is derived from their data even with the gate removed. It is recorded
here as this server's reading of the rule, the same unanswered question as the
device store in §11 of that document, and not as a ruling.

── ONE OBJECT PER FLIGHT, OUTSIDE THE STATE PREFIX ─────────────────────────────

diag/<NUMBER>/<DATE>.json in the same bucket. The prefix is what keeps it out of
pollstate's five-day sweep, which only walks state/. It has its own sweep, below,
run from every poll pass.

Written with a generation precondition and retried on contention, because the
poller and the dispatcher are separate requests and both write here.
"""
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

import gcs
import pollstate

logger = logging.getLogger("diag")

PREFIX = "diag/"
DIAG_VALUES_DAYS = 6
DIAG_KEEP_DAYS = 30
MAX_EVENTS = 2000
WRITE_ATTEMPTS = 4


def _targets():
    """{(NUMBER, date)} from DIAG_FLIGHTS, read on every call.

    READ LIVE RATHER THAN AT IMPORT so the list can be changed with
    --update-env-vars and no code change, and cleared the same way when the
    review is done. "KL606:2026-09-23,KL877:2026-09-24".
    """
    out = set()
    for item in (os.getenv("DIAG_FLIGHTS") or "").split(","):
        num, _, day = item.strip().partition(":")
        if num and day:
            out.add((num.strip().upper(), day.strip()))
    return out


def _device():
    return (os.getenv("DIAG_DEVICE") or "").strip()


def watching(number, day):
    return (str(number or "").strip().upper(), str(day or "").strip()) in _targets()


def _key(number, day):
    return "%s%s/%s.json" % (PREFIX, str(number).strip().upper(), str(day).strip())


def _iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(raw):
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── STORAGE, WITH AN IN-PROCESS FALLBACK FOR TESTS ──────────────────────────

_local = {}


def _read(key):
    bucket = pollstate._bucket()
    if bucket is None:
        return _local.get(key), None
    try:
        blob = bucket.get_blob(key)
        if blob is None:
            return None, None
        return json.loads(blob.download_as_bytes().decode("utf-8")), blob.generation
    except Exception:  # noqa: BLE001
        return None, None


def _write(key, doc, generation):
    bucket = pollstate._bucket()
    if bucket is None:
        _local[key] = doc
        return True
    try:
        bucket.blob(key).upload_from_string(
            json.dumps(doc, separators=(",", ":")),
            content_type="application/json",
            if_generation_match=0 if generation is None else generation,
        )
        return True
    except Exception:  # noqa: BLE001 -- a lost diagnostic write must never fail a poll
        return False


def _mutate(number, day, apply_fn):
    key = _key(number, day)
    for attempt in range(WRITE_ATTEMPTS):
        doc, gen = _read(key)
        new = apply_fn(doc)
        if new is None:
            return True
        if _write(key, new, gen):
            return True
        time.sleep(min(1.5, 0.15 * (2 ** attempt)) * (0.5 + random.random()))
    logger.warning("diag: could not write %s after %d attempts", key, WRITE_ATTEMPTS)
    return False


def _blank(number, day, now):
    return {"version": 1, "flight_number": str(number).upper(), "flight_date": day,
            "device_id": _device(), "created_at": _iso(now),
            "kinds": {}, "slots_seen": {}, "events": []}


def _append(doc, events):
    doc["events"] = (list(doc.get("events") or []) + events)[-MAX_EVENTS:]
    return doc


# ── WHAT THE POLLER DID ─────────────────────────────────────────────────────

def note_poll(number, day, now, record, changes, messages, suppressed):
    """One poll, and every notification it decided or decided against.

    NEVER RAISES. A diagnostic that could fail a poll would be a diagnostic
    that changed the thing it was watching.
    """
    try:
        if not watching(number, day):
            return
        poll = {
            "at": _iso(now), "type": "poll", "tier": record.get("tier"),
            "adb": bool(record.get("adb")), "fr24": bool(record.get("fr24")),
            "skipped": record.get("skipped"),
            "adb_error": record.get("adb_error"), "fr24_error": record.get("fr24_error"),
            "notify_error": record.get("notify_error"),
            # THE FIELD NAMES ARE THE SKELETON; WHAT THEY CHANGED TO IS NOT.
            "changed": [c.get("field") for c in (changes or [])],
            "values": {c.get("field"): {"from": c.get("from"), "to": c.get("to")}
                       for c in (changes or [])},
        }
        events = [poll]
        kinds = {}
        for m in messages or []:
            kinds[m.get("key")] = m.get("kind")
            events.append({
                "at": _iso(now), "type": "decided", "kind": m.get("kind"),
                "key": m.get("key"), "deliver_after": m.get("deliver_after"),
                "values": {"values": m.get("values")},
            })
        for s in suppressed or []:
            events.append({"at": _iso(now), "type": "decided_against",
                           "kind": s.get("kind"), "reason": s.get("reason")})

        def apply(doc):
            d = doc or _blank(number, day, now)
            d["kinds"] = dict(d.get("kinds") or {}, **kinds)
            return _append(d, events)
        _mutate(number, day, apply)
    except Exception:  # noqa: BLE001
        logger.exception("diag: note_poll failed for %s/%s", number, day)


# ── WHAT THE DISPATCHER DID ─────────────────────────────────────────────────
#
# DISPATCH ALREADY KEEPS THE WHOLE LIFECYCLE, in slots inside the poll state:
# sent_at and a ticket, a receipt and its status, gave_up with a drop_reason or a
# send_error. This reads those slots after each pass and records each STAGE the
# first time it is seen -- so a slot that is sent, then delivered, produces two
# events and not one per pass for the rest of the day.
#
# ONLY THE DIAG DEVICE'S SLOTS. A slot id is "<message key>|<device id>", and a
# flight watched from three phones has three slots per message; only hers are
# the question.

def _stages(slot):
    """[(stage, reason)] this slot has reached, in the order they happen."""
    out = []
    if slot.get("send_error") and not slot.get("gave_up") and not slot.get("sent_at"):
        out.append(("send_failed", slot.get("send_error")))
    if slot.get("sent_at"):
        out.append(("sent", None))
    status = slot.get("receipt_status")
    if status == "ok":
        out.append(("delivered", None))
    elif status == "expired":
        out.append(("expired", "no receipt within a day"))
    elif status:
        out.append(("not_delivered", slot.get("receipt_error") or status))
    if slot.get("gave_up"):
        out.append(("dropped", slot.get("drop_reason") or slot.get("send_error")))
    return out


def note_dispatch(now):
    """Record every new delivery stage for the diag device. Never raises."""
    try:
        device = _device()
        if not device:
            return
        for number, day in _targets():
            state, _ = pollstate.read_state(number, day)
            sent = (state or {}).get("sent")
            if not isinstance(sent, dict):
                continue
            mine = {sid: s for sid, s in sent.items()
                    if str(sid).endswith("|" + device) and isinstance(s, dict)}
            if not mine:
                continue

            def apply(doc, mine=mine, number=number, day=day):
                d = doc or _blank(number, day, now)
                seen = dict(d.get("slots_seen") or {})
                kinds = d.get("kinds") or {}
                new = []
                for sid, slot in mine.items():
                    done = set(seen.get(sid) or [])
                    key = str(sid).split("|", 1)[0]
                    for stage, reason in _stages(slot):
                        if stage in done:
                            continue
                        done.add(stage)
                        new.append({"at": _iso(now), "type": stage,
                                    "kind": kinds.get(key) or slot.get("kind"),
                                    "key": key, "reason": reason})
                    seen[sid] = sorted(done)
                if not new:
                    return None
                d["slots_seen"] = seen
                return _append(d, new)
            _mutate(number, day, apply)
    except Exception:  # noqa: BLE001
        logger.exception("diag: note_dispatch failed")


# ── AND THE SWEEP ───────────────────────────────────────────────────────────
#
# RUN FROM EVERY POLL PASS, because the flights stop writing here the day they
# land and something still has to strip their values on the sixth day. It walks
# only diag/, lists a handful of objects, and writes only when an event's values
# have crossed the line or a whole object has.

def sweep(now=None):
    now = now or datetime.now(timezone.utc)
    cut_values = now - timedelta(days=DIAG_VALUES_DAYS)
    cut_all = now - timedelta(days=DIAG_KEEP_DAYS)
    bucket = pollstate._bucket()
    keys = list(_local) if bucket is None else \
        [b.name for b in bucket.list_blobs(prefix=PREFIX)]
    stripped = deleted = 0
    for key in keys:
        doc, gen = _read(key)
        if not doc:
            continue
        created = _parse(doc.get("created_at"))
        if created is not None and created < cut_all:
            if bucket is None:
                _local.pop(key, None)
            else:
                try:
                    bucket.blob(key).delete(if_generation_match=gen)
                except Exception:  # noqa: BLE001
                    continue
            deleted += 1
            continue
        changed = False
        for ev in doc.get("events") or []:
            at = _parse(ev.get("at"))
            if "values" in ev and at is not None and at < cut_values:
                del ev["values"]
                ev["values_stripped"] = True
                changed = True
                stripped += 1
        if changed:
            _write(key, doc, gen)
    return {"stripped": stripped, "deleted": deleted}
