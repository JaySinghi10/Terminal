// What the server found when a flight was cancelled, and the only file that
// talks to the /alternatives endpoint.
//
// ── THE DEVICE DOES NO SEARCHING, AND THAT IS THE WHOLE DESIGN ──────────────
//
// The poller walks the departure board at the moment a cancellation is seen,
// judges every row against the next leg the passenger is booked on, and stores
// the result beside that flight's state. This reads it back. No provider call
// happens on this path -- not here, not in the endpoint -- which is what lets
// the drawer open at once and what stops a screen nobody scrolls costing units.
//
// ── AND NOTHING IS CACHED ON THE DEVICE, DELIBERATELY ───────────────────────
//
// These rows are provider data under a seven-day ceiling; docs/connection-
// search.md §1 records AeroDataBox's own ruling that reshaping board data does
// not make it anything else. §11 of the same document is the OPEN question:
// SavedFlight DTOs are written to AsyncStorage and never deleted by age, and
// whether that already breaches the limit has not been put to the provider.
//
// Writing board rows to disk would extend an unresolved exposure to a second
// class of data while the first is still unanswered. Held in memory for as long
// as the drawer is open and dropped when it closes, they are never stored at
// all -- and server-side they expire with the state object at five days.
//
// SO A CLOSED DRAWER REMEMBERS NOTHING and re-opening fetches again. That is a
// round trip against an endpoint that touches no provider, which is fast enough
// to read as instant and is the price of not keeping what we are not sure we
// may keep.
import { deviceId, WATCH_SECRET } from './watch';
import type { SavedFlight } from './storage';

// ── WOULD THIS REPLACEMENT STILL MAKE THE NEXT LEG ──────────────────────────
//
// The server's verdict, not this file's -- every one of these is decided in
// notify.classify_alternatives against the same minimum the connection warning
// uses, so a row and the warning about the leg it replaces cannot disagree.
//
// null IS NOT A FAILURE. It means there is no next leg to make: a final leg, or
// a journey the server could not pair. Every row is then simply a flight to the
// destination, which is the whole question.
//
// 'unknown' IS NOT 'no' EITHER, and it is the one worth knowing about. A board
// row can name a destination airport and carry no arrival time at all. Such a
// row is a real flight to the right place that cannot be tested against a
// connection -- so it is shown, marked, and kept out of the connection list.
export type Connects = 'comfortable' | 'at_risk' | 'will_miss' | 'unknown' | null;

export type AlternativeRow = {
  flightNumber: string;
  airline: string | null;
  destinationIata: string | null;
  departureIso: string | null;
  arrivalIso: string | null;
  arrivalLabel: string | null;
  // The three the push already renders, carried so a row and the sentence about
  // it cannot come to disagree about which day it leaves.
  time: string;
  tz: string | null;
  day: string;
  date: string;
  connects: Connects;
  layoverMinutes: number | null;
  minimumMinutes: number | null;
};

export type NextLegBrief = {
  flightNumber: string | null;
  departureIata: string | null;
  arrivalIata: string | null;
  departureIso: string | null;
  departureLabel: string | null;
};

export type Alternatives = {
  // WHEN THE SEARCH RAN, not when this was fetched. The drawer shows the age of
  // the ANSWER; a fetch a second ago over a search from this morning is a
  // search from this morning.
  searchedAt: string | null;
  daysSearched: number;
  // Whether the walk finished. false means the poller is still working through
  // its days, which is a different thing to say than "there is nothing".
  done: boolean;
  maxDays: number;
  origin: string | null;
  destination: string | null;
  nextLeg: NextLegBrief | null;
  rows: AlternativeRow[];
};

function str(v: unknown): string | null {
  return typeof v === 'string' && v !== '' ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function verdict(v: unknown): Connects {
  return v === 'comfortable' || v === 'at_risk' || v === 'will_miss' || v === 'unknown'
    ? v : null;
}

/**
 * One read. Never throws, and never invents a block it did not receive.
 *
 * null MEANS "NOTHING STORED", AND THAT COVERS SEVERAL CAUSES ON PURPOSE. The
 * endpoint answers identically whether this device does not own the flight,
 * whether nothing has been searched yet, or whether the watch store could not
 * be read -- so that a caller cannot use it to learn which flights a device
 * watches. The drawer needs no distinction: with nothing stored it says the
 * search is still running, which is true in every one of those cases.
 */
export async function fetchAlternatives(
  apiBase: string, f: SavedFlight,
): Promise<Alternatives | null> {
  try {
    const params = [
      `date=${encodeURIComponent(f.flightDate)}`,
      `device_id=${encodeURIComponent(await deviceId())}`,
    ];
    const r = await fetch(
      `${apiBase}/alternatives/${encodeURIComponent(f.flightNumber)}?${params.join('&')}`,
      { headers: { 'X-Watch-Secret': WATCH_SECRET } },
    );
    if (!r.ok) return null;
    const body = await r.json() as { alternatives?: unknown };
    const a = body?.alternatives;
    if (a === null || a === undefined || typeof a !== 'object') return null;
    const raw = a as Record<string, unknown>;
    const rows = Array.isArray(raw.rows) ? raw.rows : [];
    const leg = raw.next_leg as Record<string, unknown> | null | undefined;
    return {
      searchedAt: str(raw.searched_at),
      daysSearched: num(raw.days_searched) ?? 0,
      done: raw.done === true,
      maxDays: num(raw.max_days) ?? 7,
      origin: str(raw.origin),
      destination: str(raw.destination),
      nextLeg: leg
        ? {
          flightNumber: str(leg.flight_number),
          departureIata: str(leg.departure_iata),
          arrivalIata: str(leg.arrival_iata),
          departureIso: str(leg.departure_scheduled_iso),
          departureLabel: str(leg.departure_scheduled),
        }
        : null,
      rows: rows.map((r0) => {
        const row = r0 as Record<string, unknown>;
        return {
          flightNumber: str(row.flight_number) ?? '',
          airline: str(row.airline),
          destinationIata: str(row.destination_iata),
          departureIso: str(row.departure_scheduled_iso),
          arrivalIso: str(row.arrival_scheduled_iso),
          arrivalLabel: str(row.arrival_scheduled),
          time: str(row.time) ?? '',
          tz: str(row.tz),
          day: str(row.day) ?? '',
          date: str(row.date) ?? '',
          connects: verdict(row.connects),
          layoverMinutes: num(row.layover_minutes),
          minimumMinutes: num(row.minimum_minutes),
        };
      }).filter(r1 => r1.flightNumber !== ''),
    };
  } catch {
    return null;
  }
}

// ── THE TWO LISTS, SPLIT ONCE ───────────────────────────────────────────────
//
// THE SPLIT IS A RULE AND NOT A FILTER WRITTEN AT A CALL SITE. A row belongs in
// the connection list only when the server says it makes the connection, which
// is 'comfortable' or 'at_risk' and nothing else:
//
//   'will_miss'   lands too late. It is still a flight to the destination.
//   'unknown'     has no arrival time, so it cannot be tested. Also still a
//                 flight to the destination, and marked as untestable there.
//   null          there is no next leg at all, so there is no connection list.
//
// EVERY ROW IS IN THE DESTINATION LIST, including the ones above it. Nothing is
// dropped for failing a test: a flight that misses the connection may still be
// the flight somebody takes.
export function makesConnection(r: AlternativeRow): boolean {
  return r.connects === 'comfortable' || r.connects === 'at_risk';
}

export function connectionRows(a: Alternatives | null): AlternativeRow[] {
  if (a === null || a.nextLeg === null) return [];
  return a.rows.filter(makesConnection);
}

/** How long ago the SEARCH ran, in minutes, or null if it never did. */
export function searchAgeMinutes(a: Alternatives | null, now: number): number | null {
  if (a === null || a.searchedAt === null) return null;
  const ms = Date.parse(a.searchedAt);
  return Number.isFinite(ms) ? Math.max(0, Math.round((now - ms) / 60000)) : null;
}
