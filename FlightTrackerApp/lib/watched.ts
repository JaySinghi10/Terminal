// The device's half of the passive reader: one request for every live flight,
// and the only file that talks to /watched.
//
// ── IT READS WHAT THE SERVER ALREADY KNOWS ──────────────────────────────────
//
// The poller has been fetching every watched flight on its own schedule the
// whole time; this asks for the stored copy. No provider is called on this path
// -- not here, not in the endpoint, which asserts it in its tests -- so an open
// app can stay current once a minute and spend nothing.
//
// ONE REQUEST, ALL THE LIVE FLIGHTS. The endpoint takes repeated f=NUMBER:DATE
// and the watch store is read once for the lot, so four legs in the air window
// cost one round trip a minute rather than four.
//
// ── WHAT THIS FILE DECIDES: NOTHING ─────────────────────────────────────────
//
// Which flights are live, whether a copy is newer than what the device holds,
// and what to do with the landing are all lib/saved.tsx's, beside the helpers
// that know a flight's times. This knows how to ask and how to read the answer.
// Same split as lib/landing.ts, for the same reason: saved imports this, so
// importing departureTs back out of saved would be a cycle.
import { deviceId, WATCH_SECRET } from './watch';
import type { SavedFlight } from './storage';

export type WatchedLanding = {
  outcome: 'landed' | 'pending' | 'unknown' | 'error';
  landedUtc: string | null;
  divertedTo: string | null;
};

export type WatchedFlight = {
  flightNumber: string;
  flightDate: string;
  // THE STORED DTO, WITH ITS AGE MADE TRUE. The server adds the time since its
  // poll to data_age_seconds before answering, so savedFlightFromApi's own
  // arithmetic lands on the provider's time and updatedAt is honest. See the
  // note on /watched in api.py.
  dto: unknown;
  // When the server last asked the provider. Not when this was fetched.
  polledAt: string | null;
  landing: WatchedLanding | null;
  landingCheckedAt: string | null;
};

// THE ENDPOINT'S OWN CAP, mirrored so a longer list is trimmed here rather
// than silently by the server.
export const WATCHED_MAX = 12;

function str(v: unknown): string | null {
  return typeof v === 'string' && v !== '' ? v : null;
}

function landing(v: unknown): WatchedLanding | null {
  if (v === null || typeof v !== 'object') return null;
  const raw = v as Record<string, unknown>;
  const o = raw.outcome;
  if (o !== 'landed' && o !== 'pending' && o !== 'unknown' && o !== 'error') return null;
  return {
    outcome: o,
    landedUtc: o === 'landed' ? str(raw.landed_utc) : null,
    divertedTo: str(raw.diverted_to),
  };
}

/**
 * One read for every flight given. Never throws; an empty list means "no
 * update this minute" and the caller keeps what it has.
 *
 * A FLIGHT THE SERVER DOES NOT RETURN IS SIMPLY ABSENT. That covers a flight
 * this device does not watch, one with no provider record yet, one whose state
 * could not be read, and an unreadable watch store -- the endpoint answers all
 * four identically on purpose, so nothing here needs to tell them apart.
 */
export async function fetchWatched(
  apiBase: string, flights: SavedFlight[],
): Promise<WatchedFlight[]> {
  if (flights.length === 0) return [];
  try {
    const pairs = flights.slice(0, WATCHED_MAX)
      .map(f => `f=${encodeURIComponent(`${f.flightNumber}:${f.flightDate}`)}`);
    const r = await fetch(
      `${apiBase}/watched?device_id=${encodeURIComponent(await deviceId())}&${pairs.join('&')}`,
      { headers: { 'X-Watch-Secret': WATCH_SECRET } },
    );
    if (!r.ok) return [];
    const body = await r.json() as { flights?: unknown };
    if (!Array.isArray(body?.flights)) return [];
    const out: WatchedFlight[] = [];
    for (const item of body.flights) {
      if (item === null || typeof item !== 'object') continue;
      const raw = item as Record<string, unknown>;
      const num = str(raw.flight_number);
      const day = str(raw.flight_date);
      if (num === null || day === null || raw.dto === null || typeof raw.dto !== 'object') continue;
      out.push({
        flightNumber: num.toUpperCase(),
        flightDate: day,
        dto: raw.dto,
        polledAt: str(raw.polled_at),
        landing: landing(raw.landing),
        landingCheckedAt: str(raw.landing_checked_at),
      });
    }
    return out;
  } catch {
    return [];
  }
}
