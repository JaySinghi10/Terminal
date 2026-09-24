// THE CONNECTION SEARCH'S STREAM, AS STATE. Pure: no React, no network, no
// native module, so tools/test_connections_client.mjs can run every line of it
// under node. The fetch that feeds it is lib/connectionStream.ts; the provider
// that holds the state is lib/routeResults.tsx.
//
// THE SERVER SENDS ONE JSON OBJECT PER LINE (GET /connections?stream=1):
//
//   {"type":"direct", ...}     the direct search's own body, which the app
//                              already has -- ignored here
//   {"type":"plan", hub_days}  how many hub-days there are to resolve
//   {"type":"hub", hub, itineraries}
//                              everything through that hub so far; a later
//                              event for the same hub REPLACES it
//   {"type":"progress", resolved, total}
//   {"type":"done", itineraries, complete, unchecked, deferred, error, ...}
//
// A LINE CAN ARRIVE IN PIECES. The network hands over chunks, and a chunk
// boundary falls wherever it falls -- inside a line, between two, or in the
// middle of a multi-byte character (which the decoder upstream handles). The
// splitter below holds the unfinished tail until its newline arrives.

// ── THE WIRE ────────────────────────────────────────────────────────────────
//
// GENERIC IN THE LEG so this file needs nothing from routeResults: the provider
// instantiates it with its own RouteFlight.
export type WireItinerary<L> = {
  kind: 'via';
  legs: [L, L];
  hub: string;
  overnight: boolean;
  international: boolean;
  // §8. Every itinerary is labelled; see docs/connection-search.md.
  transfer: 'self' | 'same_carrier';
};

export type ConnEvent<L> =
  | { type: 'direct' }
  | { type: 'plan'; hub_days: number; hubs: string[] }
  | { type: 'hub'; hub: string; day: string; itineraries: WireItinerary<L>[] }
  | { type: 'progress'; resolved: number; total: number }
  | {
    type: 'done';
    itineraries: WireItinerary<L>[];
    complete: boolean;
    unchecked: string[];
    deferred?: boolean;
    error: string | null;
    units_spent?: number;
  };

// ── THE STATE ───────────────────────────────────────────────────────────────
//
//   idle       nothing asked for this route
//   loading    the stream is open
//   done       the stream finished; `complete` says whether it is a proof
//   deferred   an automatic search the server declined because the month's
//              units are below the connections threshold -- the button appears
//   error      the stream failed; the button appears so it can be tried again
//
// `key` NAMES THE SEARCH the state belongs to -- origin, destination, date -- so
// an event from a search the user has already moved on from can be recognised
// and dropped by the provider instead of landing on the wrong route.
export type ConnState<L> = {
  status: 'idle' | 'loading' | 'done' | 'deferred' | 'error';
  key: string | null;
  byHub: Record<string, WireItinerary<L>[]>;
  final: WireItinerary<L>[] | null;
  resolved: number;
  total: number | null;
  complete: boolean;
  unchecked: string[];
  error: string | null;
};

export function connIdle<L>(): ConnState<L> {
  return {
    status: 'idle', key: null, byHub: {}, final: null,
    resolved: 0, total: null, complete: false, unchecked: [], error: null,
  };
}

export function connLoading<L>(key: string): ConnState<L> {
  return { ...connIdle<L>(), status: 'loading', key };
}

export function connKey(origin: string, destination: string, day: string | null): string {
  return `${origin}-${destination}-${day ?? 'rolling'}`;
}

// ONE EVENT, FOLDED IN. Never mutates. An event after "done" changes nothing: the
// server sends none, and a stray one must not reopen a finished answer.
export function connReduce<L>(s: ConnState<L>, ev: ConnEvent<L>): ConnState<L> {
  if (s.status !== 'loading') return s;
  switch (ev.type) {
    case 'plan':
      return { ...s, total: ev.hub_days };
    case 'hub':
      return { ...s, byHub: { ...s.byHub, [ev.hub]: ev.itineraries } };
    case 'progress':
      return { ...s, resolved: ev.resolved, total: ev.total };
    case 'done':
      if (ev.deferred) return { ...s, status: 'deferred' };
      if (ev.error) return { ...s, status: 'error', error: ev.error };
      return {
        ...s,
        status: 'done',
        final: ev.itineraries,
        complete: ev.complete,
        unchecked: ev.unchecked,
        resolved: s.total ?? s.resolved,
      };
    default:
      return s;
  }
}

// WHAT THE LIST SHOWS. The server's own ranked answer once it is done; until
// then everything the hub events have carried, which the list sorts itself.
export function connItineraries<L>(s: ConnState<L>): WireItinerary<L>[] {
  if (s.final !== null) return s.final;
  return Object.values(s.byHub).flat();
}

// MAY A CONNECTION BE CALLED THE FASTEST? Only when the search finished and says
// it is complete: an unfetched hub-day might have held a faster journey, and a
// search still running has not looked yet. docs/connection-search.md §12.
export function connFastestAllowed<L>(s: ConnState<L>): boolean {
  return s.status === 'done' && s.complete;
}

// ── THE LINE SPLITTER ───────────────────────────────────────────────────────
//
// Feed it decoded text as it arrives; it returns the lines that are now whole
// and keeps the rest. Empty lines are dropped. Call it with a final '\n' at the
// end of the stream to flush a last line the server sent without one.
export function lineSplitter(): (text: string) => string[] {
  let tail = '';
  return (text: string) => {
    tail += text;
    const parts = tail.split('\n');
    tail = parts.pop() ?? '';
    return parts.map(p => p.trim()).filter(p => p !== '');
  };
}
