// WHEN A FLIGHT CAME DOWN, AND HOW IT DID AGAINST ITS TIMETABLE.
//
// THE RULE LIVES HERE AND ITS READERS CALL lib/saved.tsx, as with
// lib/departure.ts and for the same reason: arrivalOutcome there supplies the
// effective status, and this file imports nothing from React Native, so
// tools/test_arrival.mjs can run it under plain node.
//
// ── THE TOUCHDOWN, WHEREVER THERE IS ONE ───────────────────────────────────
//
// "LANDED" MEANS THE WHEELS, so the time it names is a touchdown: FR24's, or the
// provider's own runway time. It is also the only arrival there is at the
// moment the aircraft comes down -- the gate time follows minutes later, and at
// airports where the provider reports no arrivals it never comes at all -- and
// it is the figure the landing notification sends, so the card and the push
// cannot disagree about how early a flight was.
//
// A GATE TIME IS NOT A LANDING. When all anyone has is the provider's gate
// arrival, the word is "arrived", because printing a gate time under "landed"
// would name the wrong moment.
//
// THE FIGURE IS THAT TIME AGAINST THE SCHEDULED ARRIVAL. A touchdown against a
// timetable that means the gate reads a few minutes kinder than the airline's
// own figure, which counts the taxi; the word in front of the clock says which
// moment is being measured.
import { zonedIsoToTs } from './time';
import { landedUtcToTs } from './landing';
import type { SavedFlight } from './storage';

export type ArrivalOutcome = {
  // 'landed' for a touchdown, 'arrived' for a gate time.
  word: 'landed' | 'arrived';
  at: number;
  // Against the scheduled arrival, in whole minutes, negative when early; null
  // when the record has no schedule to measure against.
  offsetMin: number | null;
};

// A MEASURED TIME IN THE FUTURE IS NOT A TIME THAT HAPPENED -- EK502 reported
// an arrival five hours ahead -- so each candidate must already be past.
function past(t: number | null, now: number): number | null {
  return t !== null && t <= now ? t : null;
}

// `effective` IS effectiveStatus(f, now), passed in. Nothing is said about a
// landing that status does not stand behind: a record whose "landed" the clock
// has refused gets no landing time here either.
export function arrivalOutcomeOf(
  f: SavedFlight, now: number, effective: string,
): ArrivalOutcome | null {
  if (effective !== 'landed') return null;
  // FR24 FIRST, THEN THE PROVIDER'S RUNWAY TIME: both are the wheels.
  const touchdown = past(landedUtcToTs(f.landedUtc), now)
    ?? past(zonedIsoToTs(f.to.runwayIso, f.to.timezone), now);
  let word: ArrivalOutcome['word'] = 'landed';
  let at = touchdown;
  if (at === null) {
    at = past(zonedIsoToTs(f.to.actualIso, f.to.timezone), now);
    // THE SERVER WRITES THE RUNWAY TIME INTO actualIso when it has no gate
    // time, and then it is a touchdown after all.
    word = f.to.actualSource === 'runway' ? 'landed' : 'arrived';
  }
  if (at === null) return null;
  const sched = zonedIsoToTs(f.to.scheduledIso, f.to.timezone);
  return { word, at, offsetMin: sched === null ? null : Math.round((at - sched) / 60_000) };
}
