// WHERE A DEPARTURE STANDS: NOT YET DUE, LATE AND COUNTING, OFF THE GATE, OR
// OFF THE GROUND.
//
// THE RULE LIVES HERE AND ITS READERS CALL lib/saved.tsx. departurePhase there
// is what every screen uses; it hands this function the flight's effective
// status, which only that file can work out. This file imports nothing from
// React Native, so tools/test_departure.mjs can run it under plain node -- the
// split lib/landing.ts already has, for the same reason.
//
// ── HOW AN AIRLINE MEASURES A LATE DEPARTURE, AND SO HOW THIS DOES ─────────
//
// FROM THE SCHEDULED TIME TO THE MOMENT THE AIRCRAFT LEAVES THE GATE. Taxiing
// is normal and is not counted. So a flight past its time with nothing
// reported is late by the minutes since that time, and the count stops at the
// gate: from then on the delay is the gate time against the schedule, which
// can be less than the count had reached if the gate time arrived late.
//
// A MEASUREMENT MOVES THIS ON; THE CLOCK NEVER DOES. The count is the one
// thing the clock drives, and it only ever says "still at the gate, this
// late". Leaving the gate needs a gate time the provider has recorded, and
// taking off needs a takeoff FR24 saw or a runway time the provider recorded.
// A departure time passing proves neither -- the rule effectiveStatus states,
// applied one level down.
import { zonedIsoToTs } from './time';
import { landedUtcToTs } from './landing';
import type { SavedFlight } from './storage';

// ── HOW EARLY A DEPARTURE MAY BE AND STILL BE THIS FLIGHT ──────────────────
//
// SIXTY MINUTES BEFORE THE SCHEDULE, the poller's FR24_TAKEOFF_EARLY_SLACK,
// for the poller's reason: FR24 is asked over a window six hours wide, and a
// number that operates twice a day puts its earlier rotation inside it. A
// takeoff an hour early is far likelier to be that rotation than this flight.
// The gate time takes the same line, where the risk is a garbled record rather
// than a second rotation, because one line is easier to hold than two.
export const EARLY_SLACK_MS = 60 * 60 * 1000;

// ── HOW LONG A TAXI IS BELIEVED WITHOUT A TAKEOFF ──────────────────────────
//
// FORTY-FIVE MINUTES FROM THE GATE. AN ESTIMATE, NOT A MEASUREMENT -- tune it
// once real departures have been watched. A taxi at a busy field can run past
// half an hour; past this, an aircraft the provider calls departed is far
// likelier airborne with nobody saying so than still on the ground, and "left
// the gate" an hour ago would be the stale claim. It then reads as every
// airborne flight did before this file: in the air, with no takeoff time.
export const TAXI_OUT_MAX_MS = 45 * 60 * 1000;

// ── HOW OLD A RECORD MAY BE AND STILL SAY THE AIRCRAFT HAS NOT LEFT ────────
//
// THIRTY MINUTES. The count claims the aircraft is still at its gate, and the
// only thing that makes that true is a provider having said so recently. The
// server asks every two minutes in the ninety before a departure, so thirty is
// fifteen missed answers. Past it the count would measure our own silence, so
// the phase is 'unknown' -- which every reader treats exactly as it treated a
// past departure before this file existed.
export const COUNT_FRESH_MS = 30 * 60 * 1000;

export type DeparturePhase =
  // Not due yet, or due this minute with nothing late about it.
  | { kind: 'before' }
  // Past its time and not gone: the larger of the minutes since the schedule
  // and the airline's own estimate, so a flight already announced forty-five
  // minutes late reads forty-five from its first minute, not one.
  | { kind: 'counting'; minutes: number }
  // Off the gate, not yet off the ground. `lateMin` is the gate time against
  // the schedule, rounded as the server rounds its own delays.
  | { kind: 'leftGate'; at: number; lateMin: number }
  // In the air, or it was. `at` when a takeoff was measured; null when the
  // provider says the flight has gone and nothing timed it.
  | { kind: 'tookOff'; at: number | null }
  // Past its time on a record too old to say, or a status nobody can place.
  | { kind: 'unknown' }
  // Cancelled or diverted: there is no departure to describe.
  | { kind: 'off' };

function scheduledTs(f: SavedFlight): number | null {
  return zonedIsoToTs(f.from.scheduledIso, f.from.timezone);
}

// AN INSTANT IS A DEPARTURE OF THIS FLIGHT IF IT HAS HAPPENED AND IS NOT
// IMPLAUSIBLY EARLY. A future one is a forecast, which is the fault the server
// found on 6E6188: an "actual" two hours ahead. With no schedule there is
// nothing to check it against, and it is refused outright, as the poller does.
function believed(t: number | null, f: SavedFlight, now: number): number | null {
  if (t === null || t > now) return null;
  const sched = scheduledTs(f);
  if (sched === null || t < sched - EARLY_SLACK_MS) return null;
  return t;
}

// FR24's TAKEOFF, WHEN IT IS ONE. Exported because effectiveStatus promotes on
// it: an aircraft seen climbing is a second source, not the clock.
export function fr24TakeoffTs(f: SavedFlight, now: number): number | null {
  return believed(landedUtcToTs(f.takeoffUtc), f, now);
}

// THE PROVIDER'S RUNWAY TIME, WHICH IS WHEELS-OFF.
function runwayTs(f: SavedFlight, now: number): number | null {
  return believed(zonedIsoToTs(f.from.runwayIso, f.from.timezone), f, now);
}

// ── THE GATE TIME, WHEN IT CAN BE BELIEVED ─────────────────────────────────
//
// A REVISED ACTUAL, NOT A RUNWAY ONE. The server writes the runway time into
// actualIso when the provider has no gate time, and that is the other clock.
//
// ON A MOVEMENT WITH LIVE COVERAGE, which is the server's _row_departed rule:
// without it a revised time can be the schedule copied across. That function's
// status veto is not needed here -- an actual only exists once the provider's
// own status says the flight has gone (movement_has_occurred), and the caller
// asks for this only when the effective status is 'active'.
function gateTs(f: SavedFlight, now: number): number | null {
  if (f.from.actualSource !== 'revised' || f.from.liveFeed !== true) return null;
  return believed(zonedIsoToTs(f.from.actualIso, f.from.timezone), f, now);
}

// `effective` IS effectiveStatus(f, now), passed in -- see the note at the top.
export function phaseOfDeparture(
  f: SavedFlight, now: number, effective: string,
): DeparturePhase {
  if (effective === 'cancelled' || effective === 'diverted') return { kind: 'off' };

  if (effective === 'active' || effective === 'landed' || effective === 'stale') {
    // A MEASURED TAKEOFF WINS OUTRIGHT, from either source.
    const took = fr24TakeoffTs(f, now) ?? runwayTs(f, now);
    if (took !== null) return { kind: 'tookOff', at: took };
    // THEN THE GATE, WHILE A TAXI IS STILL THE LIKELY STORY.
    const gate = effective === 'active' ? gateTs(f, now) : null;
    if (gate !== null && now - gate < TAXI_OUT_MAX_MS) {
      // believed() refuses a gate time with no schedule, so there is one.
      const sched = scheduledTs(f) as number;
      return { kind: 'leftGate', at: gate, lateMin: Math.round((gate - sched) / 60_000) };
    }
    return { kind: 'tookOff', at: null };
  }

  // ONLY A FLIGHT WHOSE PROVIDER SAYS IT HAS NOT GONE IS COUNTED. 'unknown' is
  // a provider with no opinion, and a count would be claiming one for it.
  if (effective !== 'scheduled') return { kind: 'unknown' };
  const sched = scheduledTs(f);
  if (sched === null || now < sched) return { kind: 'before' };
  if (now - f.updatedAt > COUNT_FRESH_MS) return { kind: 'unknown' };
  const elapsed = Math.floor((now - sched) / 60_000);
  // from.delay IS THE ESTIMATE AGAINST THE SCHEDULE while nothing has happened
  // -- the server compares like with like -- and null when there is none.
  const estimate = typeof f.from.delay === 'number' ? f.from.delay : 0;
  const minutes = Math.max(elapsed, estimate);
  return minutes > 0 ? { kind: 'counting', minutes } : { kind: 'before' };
}
