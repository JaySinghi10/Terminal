// THE ROUTE RESULTS, LIFTED OUT OF THE SEARCH SCREEN.
//
// EVERYTHING HERE WAS app/(tabs)/search/index.tsx's AND IS UNCHANGED BUT FOR
// WHERE IT LIVES. The board, the sort, the three filters, the date, the picker
// options, the bought-in arrival times, the selection, and every derivation from
// the raw rows to the one flight the bubble shows: all of it used to be state
// and consts inside the Search component, which made it visible to that
// component and nothing else.
//
// WHY IT MOVED: the results were presented in a second screen for a while --
// a native sheet, a sibling route in the same Stack -- and a sibling cannot
// read a sibling's state, so a provider in the search route's own layout sat
// above both. The sheet is the map screen's own again (components/
// ResultsSheet.tsx), and the provider stays: the sheet and the screen still
// read one board and write one sort, and neither has to own the other.
//
// WHAT DID NOT MOVE, DELIBERATELY. The pickers -- the calendar, the anchored
// filter panels, the airport disambiguators -- are Modals with measured
// anchors, and they stay on the screen that draws them. The pill-label budget
// arithmetic stays with the pills. The natural-language parser stays with the
// field. Only what the LIST is made of is here.
//
// THE HOST. runRouteLookup and saveFromRoute report through the flight card
// host's channels -- setError, the error counter, the card's own setters -- and
// the host is a hook the search screen owns. It cannot be called from here, so
// the screen BINDS it: bindHost, once per render, into a ref this file reads at
// the moment of a fetch. The same shape as the gesture's dismissRef was, for the
// same reason -- the thing being called is declared somewhere this code cannot
// reach by scope.
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppState, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { savedFlightFromApi, makeFlightId, ISO_DAY_RE } from './storage';
import { airlineFromFlightNumber } from './airlines';
import { useSaved, API_BASE, flightUrl, NO_TIME, SAVE_MSG, OWN_MSG } from './saved';
import { useToast } from './toast';
import { airportByCode, resolveAirportName } from './airports';
import type { Airport } from './airports';
// THE DETENT ARITHMETIC, which no sheet owns. See its note.
import { sheetDetents } from './sheet';
// FOR THE LINE UNDER THE PILL: a row's clock as the row prints it, and the day
// as the date pill prints it, so an answer reads in the list's own words.
import { routeDateLabel, boardClock, clockInWords } from './flightstatus';
// THE CONNECTION SEARCH. connections.ts is the stream folded into state, pure;
// connectionStream.ts is the fetch that reads it as it arrives.
import {
  connIdle, connLoading, connKey, connReduce, connItineraries, connFastestAllowed,
  type ConnState, type ConnEvent, type WireItinerary,
} from './connections';
import { streamConnections } from './connectionStream';

// Decoration the provider puts on board names that the airport dataset does
// not carry: "Bengaluru Intl Airport", "Dubai Intl (Terminal 3)", "Khorog
// Airport,Tajikistan". Each was found on a real board, not imagined.
//
// "aeroport" is here because the DATED board does not speak the same language
// as the rolling one. The airport a rolling board calls "Ayodhya" a dated board
// calls "Aeroport Ayodkhya", and Delhi and Kolkata come back as "Deli" and
// "Kalkutta". The spellings themselves are aliases in the dataset; only the
// word "aeroport" belongs here, because it is decoration rather than a name.
const ROUTE_NAME_NOISE =
  /\b(intl|int'l|international|aeroport|airport|arpt|apt|airfield|aerodrome|domestic|terminal)\b/gi;

function routeTidyName(raw: string | null | undefined): string {
  return String(raw ?? '')
    .replace(/,.*$/, '')          // "Khorog Airport,Tajikistan"
    .replace(/\(.*?\)/g, ' ')     // "Dubai Intl (Terminal 3)"
    .replace(ROUTE_NAME_NOISE, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// The airport a board name refers to, or null.
//
// The whole tidied name first, then progressively shorter LEADING phrases. The
// provider usually leads with the city and follows it with the airport's own
// name — "Delhi Indira Gandhi", "Mumbai Chhatrapati Shivaji" — and the dataset
// indexes those two separately, never that concatenation. Narrowing to "Delhi"
// is what resolves them; without it the whole string simply misses.
//
// Only ever used to ask "is this row for the destination that was searched
// for", and a wrong answer means the row is left out rather than shown wrongly.
function routeResolveDestination(raw: string | null | undefined): Airport | null {
  const tidy = routeTidyName(raw);
  if (tidy.length < 3) return null;
  // Split on hyphens too, not only spaces. normalizeTerm already turns a hyphen
  // into a space when it builds the dataset's own haystack, so leaving them
  // joined here made the two disagree: "Denpasar-Bali Island" narrowed to
  // "Denpasar-Bali" and never to "Denpasar", which is what actually resolves.
  const words = tidy.split(/[\s-]+/).filter(w => w.length > 0);
  for (let n = words.length; n >= 1; n--) {
    const candidate = words.slice(0, n).join(' ');
    if (candidate.length < 3) continue;
    const hit = resolveAirportName(candidate);
    if (hit !== null) return hit.airport;
  }
  return null;
}

// The backend fetches a 12-hour board whichever value it is sent, then filters
// down to this. At 6 half of what was already paid for was discarded, so 12 is
// strictly more for the same 2 units.
export const ROUTE_TODAY_HOURS = 12;

// Matches ROUTE_MAX_FUTURE_DAYS on the backend. Checked here too so an
// out-of-range date never reaches the network: a dated search costs 4 units.
export const ROUTE_MAX_DATE_DAYS = 60;

// ── WHERE THE RESULTS SHEET CAN REST ────────────────────────────────────────
//
// THREE HEIGHTS, MEASURED FROM THE SCREEN'S BOTTOM EDGE. The sheet is this
// app's own -- components/ResultsSheet.tsx -- drawn on the map screen under the
// tab bar, with its surface running to the screen's edge behind the bar and
// its content stopping above it. So the small height is the BAR'S INSET plus
// the head: the room the grabber takes, the green pill, and the air under it,
// so that at rest the sheet shows above the bar how the list is ordered and
// nothing of the controls row beneath. The head is the sum of the four numbers
// below, which are the head's own styles, declared here so the detent and the
// layout it is cut from cannot drift apart.
//
// THE MIDDLE AND THE LARGE ARE lib/sheet.ts's -- half and nine tenths of the
// window less a gap, shared by every sheet the shell draws. Only the small
// height is this sheet's, because only this sheet knows its head.
//
// TWO POINTS SHORT OF THE HEAD, on purpose, so the head's own bottom air is
// what the cut takes rather than the top of the controls row. The pill itself
// ends twelve points above the cut either way.
//
// THE PILL IS FIFTY TALL: seventeen above and below a sixteen-point line. With
// the fourteen of air under it the head is 86, and the small detent cuts at 84.
export const SHEET_GRABBER_CLEARANCE = 22;
export const SHEET_PILL_PAD = 17;
export const SHEET_PILL_LINE = 16;
export const SHEET_HEAD_PAD = 14;
export const SHEET_HEAD_HEIGHT =
  SHEET_GRABBER_CLEARANCE + SHEET_PILL_PAD * 2 + SHEET_PILL_LINE + SHEET_HEAD_PAD;
const SHEET_SMALL_TOLERANCE = 2;
const SHEET_SMALL_HEIGHT = SHEET_HEAD_HEIGHT - SHEET_SMALL_TOLERANCE;

// A NOTE UNDER THE PILL, when a search has one: the answer to a question, the
// origin the app assumed, the day a range was cut to. Thirteen of text on a
// sixteen line, at most two lines each, under a gap of eight -- and the small
// detent GROWS BY EXACTLY THAT, because an answer nobody can read without
// raising the sheet is not an answer. The line count is estimated from the
// window's width at SHEET_NOTE_CHAR points a character, a little wider than
// Inter's average advance at 13 so the estimate errs toward a spare line rather
// than a clipped one; the Text caps at the same count, so the cut never lands
// inside a note. Declared here for the reason the head's numbers are: the
// detent is computed from them.
export const SHEET_NOTE_LINE = 16;
export const SHEET_NOTE_GAP = 8;
export const SHEET_NOTE_MAX_LINES = 2;
export const SHEET_NOTE_CHAR = 7;
// The sheet's side padding, which the estimate above has to subtract.
export const SHEET_SIDE_PAD = 20;

// Local-only view controls. Nothing here re-fetches: every option reorders or
// hides rows already in state.
// 'latest' AND 'airline' ARE NEW, and both exist because the drawer names its
// orderings on pills rather than in a dropdown: Fastest, Earliest, Latest, by
// airline. The first two were already here under other names -- duration and
// departure -- and the other two are a reversed departure and an alphabetical
// carrier. 'arrival' stays: nothing on the new row selects it, but the sort
// itself is sound and deleting it would be deleting working code to tidy a list.
export const ROUTE_SORT_OPTIONS = ['departure', 'arrival', 'duration', 'latest', 'airline'] as const;
export type RouteSort = typeof ROUTE_SORT_OPTIONS[number];
// FASTEST, NOT EARLIEST. The bubble has always defaulted to the fastest flight
// -- see routeSelected -- and the capsule over the list used to read "Earliest
// flight" beside it, two controls disagreeing about which row the list is
// about. The default ordering is now the one the default selection was already
// taken from. Consequences: the pin is never lifted out of a default list (it
// is already first); a row still waiting on a bought-in arrival sorts last
// until the fill lands; and choosing Earliest is now a change, so it marks the
// controls dirty and Reset offers to undo it.
export const ROUTE_SORT_DEFAULT: RouteSort = 'duration';

// The bare enum values are ambiguous on a pill: "departure" could as easily mean
// a filter as an ordering. Naming the quantity being sorted on removes the
// question.
export const ROUTE_SORT_LABELS: Record<RouteSort, string> = {
  departure: 'Earliest',
  arrival: 'arrival time',
  duration: 'Fastest',
  latest: 'Latest',
  airline: 'By airline',
};

// THE FOUR ON THE DRAWER, IN THE ORDER THEY ARE READ. 'arrival' is not among
// them: these are what a person chooses between, and the capsule shows one at a
// time rather than four at once.
export const ROUTE_SORT_PILLS: RouteSort[] = ['duration', 'departure', 'latest', 'airline'];

// WHAT THE SHUT CAPSULE READS. A whole phrase rather than the option's own word,
// because the capsule is a statement about the list under it -- "Fastest flight"
// -- where the four rows inside it are choices and take the short form. 'By
// airline' is the one that cannot take the noun: "By airline flight" is not
// English, and an ordering by carrier is not a claim about any one flight.
export const ROUTE_SORT_CAPSULE: Record<RouteSort, string> = {
  duration: 'Fastest flight',
  departure: 'Earliest flight',
  latest: 'Latest flight',
  airline: 'By airline',
  arrival: 'By arrival time',
};

// What the SORT PILL shows, which is not the same thing. The panel has room to
// spell it out; the pill has an 8-character cap, and the default shows the noun
// rather than its value because a pill reading "departure" would look like a
// filter. These are the panel's own words minus the redundant "time".
export const ROUTE_SORT_PILL: Record<RouteSort, string> = {
  departure: 'Sort',
  arrival: 'arrival',
  duration: 'duration',
  latest: 'latest',
  airline: 'airline',
};

// ── HOW LONG A FLIGHT TAKES, IN WORDS ───────────────────────────────────────
//
// THE BUBBLE'S SECOND LINE AND NOTHING ELSE. Hours and minutes, zero-padded on
// the minutes so two bubbles either side of an hour are the same width.
export const routeDurLabel = (ms: number | null): string | null => {
  if (ms === null) return null;
  const total = Math.round(ms / 60000);
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, '0')}m`;
};

// Boundaries are on each airport's own wall clock, not the device's. Labelled in
// 24-hour time so the control reads in the same units as the rows.
// Chronological, so the filter panels and the group headings both read down the
// clock. bandForHour is boundary-based and does not depend on this order; every
// other use derives from it, so this line is the only place ordering lives.
export const ROUTE_BANDS = ['00:00-05:00', '05:00-12:00', '12:00-18:00', '18:00-00:00'] as const;
export type RouteBand = typeof ROUTE_BANDS[number];

export function bandForHour(h: number): RouteBand {
  if (h >= 5 && h < 12) return '05:00-12:00';
  if (h >= 12 && h < 18) return '12:00-18:00';
  if (h >= 18) return '18:00-00:00';
  return '00:00-05:00';
}

export const ALL_BANDS_ON: Record<RouteBand, boolean> =
  { '00:00-05:00': true, '05:00-12:00': true, '12:00-18:00': true, '18:00-00:00': true };

// THE ONE WORD A ROW PRINTS ABOUT ITS PROGRESS, OR NOTHING.
//
// A departure board is almost entirely routine. Printing a status on every row
// is a column of identical words that buries the one row a traveller actually
// needs to see. So a row prints a word only when it means something:
//
//   departed   the backend's flag, derived from the provider's live movement
//              times and not from its status word. The status word is not
//              believed for this: AeroDataBox returns "Departed" and "EnRoute"
//              for flights still at the gate, hours ahead of the schedule, so
//              a board read from it printed "active" on every row and told
//              nobody anything. The poller found the same and refuses the word
//              too -- see _has_departed in poller.py.
//   cancelled  the provider's word, and the one thing worth reading first.
//   diverted   likewise.
//
// Everything else -- scheduled, the provider's premature "active", "landed" on
// a board that includes the morning, "unknown" -- prints nothing. A flight
// that has landed has also departed, and reads as such; the board is a
// departure board.
export const routeStatusWord = (r: RouteFlight): 'departed' | 'cancelled' | 'diverted' | null =>
  r.status === 'cancelled' || r.status === 'diverted' ? r.status
    : r.departed === true ? 'departed'
      : null;

// Only the fields actually rendered. `airline` is deliberately absent: the
// provider mislabels at least one carrier (QP comes back as "Starlight
// Airline", not Akasa Air), and the two-letter prefix of flight_number is the
// reliable identifier. Omitting it here makes rendering it a type error.
export type RouteFlight = {
  flight_number: string;
  // Null when the provider named the destination without coding it. Rows that
  // reach the rendered list always have one: routeRecovered fills it in from
  // destination_airport, and a row whose name resolves to nothing never gets
  // there. The type stays honest about the wire.
  destination_iata: string | null;
  // The provider's own name for the destination. Present on every row; the only
  // identifier the null-code ones carry.
  destination_airport?: string | null;
  departure_scheduled: string;
  departure_scheduled_iso: string | null;
  // Null when the board carried no arrival time for this row at all. The
  // backend sends the key with a null value rather than omitting it.
  arrival_scheduled: string | null;
  arrival_scheduled_iso: string | null;
  // THE AIRPORT THIS ROW LEAVES FROM. It used to be implied by the board the
  // row came off, and every reader took it from routeResult.origin. A
  // connecting itinerary's second leg leaves from the hub, so a leg carries its
  // own. Optional so a response from an older backend still parses, and null
  // when the provider named the departure airport without coding it; readers
  // go through legOrigin, which falls back to the board's origin either way.
  origin_iata?: string | null;
  status: string;
  // WHETHER THE FLIGHT HAS ACTUALLY LEFT, decided on the backend from the
  // provider's live movement times: the scheduled time has passed, the
  // departure has live coverage, and a runway or revised time is in the past.
  // Never from the status word, which the provider sets to "Departed" ahead of
  // the event. Optional so a response from an older backend still parses; a
  // row without it prints no progress word, which is the safe reading.
  departed?: boolean;
};

export type RouteResult = {
  origin: string;
  destination: string;
  window_hours: number;
  // The local calendar date the board was fetched for, or null for the rolling
  // window from now. window_hours does not apply to a dated search.
  date: string | null;
  count: number;
  total_found: number;
  truncated: boolean;
  flights: RouteFlight[];
  // Rows the backend could not match, because the board named the destination
  // without coding it. Candidates, not results: they are not in count,
  // total_found or truncated. Optional so a response from an older backend
  // still parses.
  unresolved?: RouteFlight[];
};

// Shown when a row has no arrival time of any kind. An em dash says "not known"
// in the width of a glyph; the "N/A" that used to arrive here said it in the
// width of a word and read as an error rather than as a gap. The font already
// renders this dash elsewhere in the file at MONO_BOLD.
export const ROUTE_NO_TIME = '—';

// HOW MANY MISSING ARRIVALS ARE WORTH BUYING, per search. Each one is a
// flight-number lookup at 2 units, so this caps a search's extra spend at 6.
//
// Counted from the boards already on disk rather than guessed: whole-airport
// departure boards carry no arrival time on 1.6% to 6.3% of rows (6/384, 6/375,
// 18/394, 10/159). A route search filters that to at most 25 rows for one
// destination, and of eighteen cached result envelopes seventeen had none at
// all and one had a single row. So the ordinary answer is zero, sometimes one.
//
// 3 covers every case observed across about 1,300 rows with room to spare. Past
// that the board is not merely unlucky, it is anomalous — feed missing on the
// provider's side, most likely — and that is precisely when quietly spending 20
// units chasing it is the wrong thing to do. The extra rows keep their dash.
const ROUTE_FILL_MAX = 3;

// The local calendar date a row DEPARTS on, read from its own ISO rather than
// from the board's date: an undated board is a rolling twelve hours, so its late
// rows belong to tomorrow. Module scope because the fill effect needs it before
// the component's own copy is in scope, and both must agree — the date decides
// WHICH instance of a flight number gets fetched.
export function routeDayOf(r: { departure_scheduled_iso: string | null }): string | null {
  const d = (r.departure_scheduled_iso ?? '').slice(0, 10);
  return ISO_DAY_RE.test(d) ? d : null;
}

// The ROUTE payload's *_iso fields carry a TRUE UTC offset, so Date.parse
// reads them correctly. That is NOT true of the *_iso fields on the flight DTO
// path: those carry a bogus +00:00 over local wall-clock digits and must go
// through zonedIsoToTs. The two paths deliberately do not share a helper for
// turning an ISO into an INSTANT, because one correct-looking swap would
// silently shift every value. clock24 is not an exception to that: it reads
// the digits as text and never computes an instant at all, which is exactly
// why one of it can serve both paths. Everything below parses through this
// one function.
const routeTs = (iso: string | null): number | null => {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
};

// ── ONE OPTION IN THE LIST: A DIRECT FLIGHT, OR A CONNECTION THROUGH ONE HUB ──
//
// THE WIRE ROW IS WRAPPED, NOT EXTENDED, AND THAT IS THE WHOLE POINT. An option
// has no flight_number, no departure_scheduled_iso and no destination_iata of
// its own, so any derivation that still reads a row's field off an option fails
// to compile rather than quietly reading the first leg of a two-leg journey.
// Everything below the accessors -- the sorts, the bands, the airline filter,
// the fastest marker, the selection -- reads through them and through nothing
// else.
//
// TODAY EVERY OPTION IS DIRECT. The 'via' member exists so the accessors are
// written for both shapes at once; nothing produces one yet, and the row, the
// sheet and the bubble render nothing for it until the connection search
// arrives. A direct option is therefore, to every reader, exactly the row it
// wraps.
export type RouteLeg = RouteFlight;
export type RouteDirect = { kind: 'direct'; leg: RouteLeg };
export type RouteItinerary = {
  kind: 'via';
  // In the order flown. The second departs from `hub`, which is the first's
  // destination.
  legs: [RouteLeg, RouteLeg];
  hub: string;
  // The second leg departs on a later local date than the first arrives.
  overnight: boolean;
  // Either leg crosses a border, which is what raises the minimum layover.
  international: boolean;
  // §8 of docs/connection-search.md. EVERY itinerary is assembled from two
  // independent boards, so every one carries a label: different carriers are a
  // self-transfer, and the same carrier is still not shown to be a through-fare.
  transfer: 'self' | 'same_carrier';
};
export type RouteOption = RouteDirect | RouteItinerary;

// §8's two sentences, fitted to the row. The row gives them two lines.
export const TRANSFER_LABEL: Record<RouteItinerary['transfer'], string> = {
  self: 'Self-transfer',
  same_carrier: 'Not a through-fare',
};
export const TRANSFER_NOTE: Record<RouteItinerary['transfer'], string> = {
  self: 'Separate bookings. Bags are not checked through and a delay is not protected.',
  same_carrier: 'Terminal built this connection; the airline may not sell it as one.',
};

// A LEG'S OWN KEY: number and departure instant, which is what routeRowKey has
// always been. An option's key is its legs' keys joined with '+', so a
// connection's key can never collide with a direct row's -- no direct key
// contains a '+' -- and the sheet's React keys and the bubble's selection stay
// unique across both shapes.
export const legKey = (r: RouteLeg): string => `${r.flight_number}-${r.departure_scheduled_iso ?? ''}`;
export const optKey = (o: RouteOption): string =>
  o.kind === 'direct' ? legKey(o.leg) : `${legKey(o.legs[0])}+${legKey(o.legs[1])}`;

export const optLegs = (o: RouteOption): RouteLeg[] => (o.kind === 'direct' ? [o.leg] : o.legs);
export const optFirst = (o: RouteOption): RouteLeg => (o.kind === 'direct' ? o.leg : o.legs[0]);
export const optLast = (o: RouteOption): RouteLeg => (o.kind === 'direct' ? o.leg : o.legs[1]);

// THE TWO ENDS OF THE JOURNEY: first departure, last arrival. On a direct
// option both are the row's own, so every band and every sort key below is
// what it was.
export const optDepIso = (o: RouteOption): string | null => optFirst(o).departure_scheduled_iso;
export const optArrIso = (o: RouteOption): string | null => optLast(o).arrival_scheduled_iso;

// Null whenever either end is missing or the pair is nonsensical, so a row
// simply renders no duration rather than a placeholder.
export const legDurationMs = (r: RouteLeg): number | null => {
  const dep = routeTs(r.departure_scheduled_iso);
  const arr = routeTs(r.arrival_scheduled_iso);
  if (dep === null || arr === null || arr <= dep) return null;
  return arr - dep;
};

// THE WHOLE JOURNEY, RECOMPUTED HERE AND NEVER TAKEN OFF THE WIRE. The fills
// can change a leg's arrival after the list is on screen, and a total carried
// from the server would go stale at exactly the moment the sort key must not.
// Reading the ends through the accessors means a filled leg moves the option
// in the duration sort the same way it moves a direct row today.
export const optDurationMs = (o: RouteOption): number | null => {
  const dep = routeTs(optDepIso(o));
  const arr = routeTs(optArrIso(o));
  if (dep === null || arr === null || arr <= dep) return null;
  return arr - dep;
};

// THE WAIT AT THE HUB, on the same rule and for the same reason. Null on a
// direct option, and null when either instant is missing; a negative gap is
// returned as it stands, because it is a contradiction worth seeing rather
// than a duration worth hiding.
export const optLayoverMs = (o: RouteOption): number | null => {
  if (o.kind === 'direct') return null;
  const arr = routeTs(o.legs[0].arrival_scheduled_iso);
  const dep = routeTs(o.legs[1].departure_scheduled_iso);
  if (arr === null || dep === null) return null;
  return dep - arr;
};

// Unmapped carriers group under their two-letter prefix rather than being left
// out of the filter. Excluding them would make those rows unfilterable, and
// would let "turn every airline off" still leave flights on screen.
export const legCarrier = (r: RouteLeg): string => {
  const name = airlineFromFlightNumber(r.flight_number);
  if (name !== null) return name;
  const m = /^([A-Z]{2}|[A-Z]\d|\d[A-Z])/.exec(r.flight_number);
  return m ? m[1] : r.flight_number;
};

// EVERY CARRIER ON THE OPTION, deduplicated. One on a direct row; one or two on
// a connection. The airline filter hides an option when ANY of these is
// switched off, and the option counts under each of them, so the count beside
// a carrier says what enabling it would show.
export const optCarriers = (o: RouteOption): string[] =>
  Array.from(new Set(optLegs(o).map(legCarrier)));

export const optDayOf = (o: RouteOption): string | null => routeDayOf(optFirst(o));

// WHERE A LEG LEAVES FROM, with the board's origin as the fallback for a row
// the provider did not code -- or a row from a backend that predates the field.
export const legOrigin = (r: RouteLeg, fallback: string): string => r.origin_iata ?? fallback;

// ── CAN THIS FLIGHT STILL BE CAUGHT ──────────────────────────────────────────
//
// A LIST THAT TREATS EVERY ROW AS BOOKABLE IS WRONG AT 19:05, when it marks a
// 20:00 departure as the fastest flight and nobody can board it. So every
// option is banded by the time left to its first departure, against the
// airport's own deadlines rather than the airline's: check-in closes at
// roughly an hour before a domestic flight and two before an international
// one, and bag drop shuts before that.
//
//   catchable    more than 1.5h to go domestic, more than 3h international.
//   risky        1h-1.5h domestic, 2h-3h international. Still listed with the
//                rest, marked in the amber the app uses for late, with a line
//                saying why.
//   uncatchable  under 1h domestic, under 2h international, or already gone
//                per the backend's departed flag. Listed BELOW the rest under
//                their own heading, never tagged fastest, still savable:
//                somebody tracking a flight they are not on needs to find the
//                one already in the air.
//
// DOMESTIC OR INTERNATIONAL IS THE TWO AIRPORTS' COUNTRIES, from the dataset
// the app ships. An airport the dataset does not know cannot be shown to be
// domestic, and the stricter deadline is the one that cannot strand anybody.
export type RouteCatch = 'catchable' | 'risky' | 'uncatchable';
const HOUR_MS = 60 * 60 * 1000;
export const CATCH_DEADLINES = {
  domestic: { risky: 1.5 * HOUR_MS, closed: 1 * HOUR_MS },
  international: { risky: 3 * HOUR_MS, closed: 2 * HOUR_MS },
} as const;
export const CATCH_RISKY_NOTE = 'Check-in is close to closing and bag drop may already be shut.';

const legInternational = (r: RouteLeg, boardOrigin: string, boardDestination: string): boolean => {
  const from = airportByCode(legOrigin(r, boardOrigin))?.country ?? null;
  const to = airportByCode(r.destination_iata ?? boardDestination)?.country ?? null;
  return from === null || to === null || from !== to;
};

// A CONNECTION IS INTERNATIONAL IF ANY LEG IS: the deadline that matters is
// the first leg's, and a domestic first leg feeding an international second
// still checks the bag through to a border.
export const optInternational = (o: RouteOption, boardOrigin: string, boardDestination: string): boolean =>
  optLegsWithOrigin(o, boardOrigin).some(({ leg, origin }) => legInternational(leg, origin, boardDestination));

// THE DEADLINES THIS OPTION IS MEASURED AGAINST, as instants: the moment it
// turns risky and the moment it closes. Null when the departure is untimed.
// Exposed so the clock below can wake exactly when a band changes.
export const optCatchBoundaries = (
  o: RouteOption, boardOrigin: string, boardDestination: string,
): { risky: number; closed: number } | null => {
  const dep = routeTs(optDepIso(o));
  if (dep === null) return null;
  const d = CATCH_DEADLINES[optInternational(o, boardOrigin, boardDestination) ? 'international' : 'domestic'];
  return { risky: dep - d.risky, closed: dep - d.closed };
};

// THE BAND, AT `now`. The departed flag wins outright: a flight the backend
// saw leave is gone whatever the clock says, and a flight the clock says has
// gone is gone whatever the flag says -- the flag is False for the first few
// minutes after a departure the provider has not confirmed. An untimed
// departure cannot be banded and is left catchable, which is the reading that
// hides nothing.
export const optCatch = (
  o: RouteOption, boardOrigin: string, boardDestination: string, now: number,
): RouteCatch => {
  if (optLegs(o).some(l => l.departed === true)) return 'uncatchable';
  const b = optCatchBoundaries(o, boardOrigin, boardDestination);
  if (b === null) return 'catchable';
  if (now >= b.closed) return 'uncatchable';
  if (now >= b.risky) return 'risky';
  return 'catchable';
};

// EACH LEG WITH ITS OWN ORIGIN, which is the shape the fills and the save need:
// a direct row and a first leg fall back to the board's origin, a second leg to
// the hub. Reading the origin any other way is how a tag flight's second leg
// would be filled with the other leg's arrival time.
export const optLegsWithOrigin = (
  o: RouteOption, boardOrigin: string,
): { leg: RouteLeg; origin: string }[] =>
  o.kind === 'direct'
    ? [{ leg: o.leg, origin: legOrigin(o.leg, boardOrigin) }]
    : [
      { leg: o.legs[0], origin: legOrigin(o.legs[0], boardOrigin) },
      { leg: o.legs[1], origin: legOrigin(o.legs[1], o.hub) },
    ];

// ── WHAT A SENTENCE ASKED, BEYOND THE ROUTE ─────────────────────────────────
//
// SET BY THE MODEL RUNG ON THE SEARCH SCREEN and read by the note under the
// pill. Every OTHER way of fetching a board -- the date pill, the end pickers,
// Reset, the pin -- passes nothing and so clears it: the question was about the
// board that was searched, and a person who has since picked an origin by hand
// no longer needs telling which one was assumed.
export type RouteQuestion = 'next' | 'first' | 'last' | 'fastest' | 'arrival' | 'count' | 'airlines';
export type RouteAsk = {
  question: RouteQuestion | null;
  // The origin nobody named, taken from the position pin. An IATA code.
  assumedOrigin: string | null;
  // A range the model cut to its first day: the user's own words for it.
  rangeLabel: string | null;
};

// ── THE HOST ────────────────────────────────────────────────────────────────
//
// WHAT A FETCH NEEDS FROM THE SCREEN THAT OWNS THE FLIGHT CARD. Every field is
// one of useFlightCardHost's own setters or values, bound by the search screen
// on every render -- see bindHost. Typed as plainly as the calls here need, so
// a React setter is assignable without a cast.
export type RouteHost = {
  setError: (message: string) => void;
  setErrorCounter: (update: (c: number) => number) => void;
  setSaveError: (message: string) => void;
  setFlight: (value: null) => void;
  setFlightRecord: (value: null) => void;
  setChatResponse: (value: null) => void;
  setLoading: (busy: boolean) => void;
  showResult: () => void;
  loading: boolean;
};

function useRouteResultsState() {
  const { savedFlights, saveRecord, saveLegs, disownFlight } = useSaved();
  const { showToast } = useToast();

  // THE SCREEN'S CHANNELS, READ AT THE MOMENT OF A FETCH. A ref rather than
  // state: binding happens during the screen's render and must not cause one.
  const host = useRef<RouteHost | null>(null);
  const bindHost = (h: RouteHost) => { host.current = h; };

  const [routeResult, setRouteResult] = useState<RouteResult | null>(null);
  // Arrival times bought one at a time for rows the board sent without one.
  // Keyed by makeFlightId, so it survives a new search: the same flight on the
  // same day is the same answer. See routeRows, which merges these in.
  const [routeFills, setRouteFills] = useState<Record<string, { text: string | null; iso: string | null }>>({});
  // Every key ever ATTEMPTED, successful or not. A ref rather than state
  // because writing it must not re-render, and because it has to outlive the
  // result it was populated from.
  const routeFillTried = useRef<Set<string>>(new Set());
  // null means Today, which sends no date parameter at all and so preserves the
  // existing relative-form search exactly.
  const [routeDate, setRouteDate] = useState<string | null>(null);
  // WHICH ROW THE BUBBLE IS SHOWING, as a key. See routeSelected for why it is
  // a key rather than a row, and for what null means.
  const [routeSelectedKey, setRouteSelectedKey] = useState<string | null>(null);
  const [routeSort, setRouteSort] = useState<RouteSort>(ROUTE_SORT_DEFAULT);
  // What each end of the current result COULD have meant. Length 1 is the
  // ordinary case and renders nothing; longer means the name did not choose
  // between airports, and the picker under the heading says which one won.
  const [routePick, setRoutePick] = useState<{ from: Airport[]; to: Airport[] } | null>(null);
  // The flight number currently being looked up and saved from a route row, or
  // null. A single slot, not a set: it doubles as the guard that stops a user
  // firing several 2-unit lookups by tapping down the list.
  const [routeSavingKey, setRouteSavingKey] = useState<string | null>(null);

  // ── THE CONNECTION SEARCH, AS IT ARRIVES ──────────────────────────────────
  //
  // ONE STREAM AT A TIME. A new route, a new day, or a new search aborts the one
  // in flight, and its `key` makes sure an event already on its way cannot land
  // on the route that replaced it.
  const [routeConn, setRouteConn] = useState<ConnState<RouteFlight>>(connIdle<RouteFlight>());
  const connAbort = useRef<AbortController | null>(null);

  const cancelConnections = () => {
    connAbort.current?.abort();
    connAbort.current = null;
    setRouteConn(connIdle<RouteFlight>());
  };

  // `auto` is true when the app starts this itself because the direct search
  // found nothing. The server may then decline, when the month's units are
  // below its connections threshold, and the sheet offers its button instead;
  // a search the person asks for is never declined for that reason.
  const startConnections = (origin: string, destination: string, day: string | null, auto: boolean) => {
    connAbort.current?.abort();
    const controller = new AbortController();
    const key = connKey(origin, destination, day);
    connAbort.current = controller;
    setRouteConn(connLoading<RouteFlight>(key));
    const onEvent = (ev: ConnEvent<RouteFlight>) => {
      // THE CONTROLLER, NOT ONLY THE KEY: restarting the same route mints the
      // same key, and the old stream's late events must not land on the new one.
      if (connAbort.current !== controller) return;
      setRouteConn(prev => (prev.key === key ? connReduce(prev, ev) : prev));
    };
    streamConnections<RouteFlight>(API_BASE, origin, destination, day, auto, onEvent, controller.signal)
      .catch(() => {
        if (controller.signal.aborted || connAbort.current !== controller) return;
        setRouteConn(prev => (prev.key === key && prev.status === 'loading'
          ? { ...prev, status: 'error', error: 'Could not load connections.' }
          : prev));
      })
      .finally(() => {
        // A stream that ended without "done" -- the connection dropped mid-way --
        // must not spin for ever.
        if (connAbort.current !== controller) return;
        setRouteConn(prev => (prev.key === key && prev.status === 'loading'
          ? { ...prev, status: 'error', error: 'The connection search stopped before it finished.' }
          : prev));
      });
  };
  const [routeDepBands, setRouteDepBands] = useState<Record<RouteBand, boolean>>(ALL_BANDS_ON);
  const [routeArrBands, setRouteArrBands] = useState<Record<RouteBand, boolean>>(ALL_BANDS_ON);
  // Exclusions rather than inclusions: the airline list is derived per result
  // set, so an empty array means "all on" without having to seed state for
  // carriers we have not seen yet.
  const [routeAirlinesOff, setRouteAirlinesOff] = useState<string[]>([]);
  // See RouteAsk. Written by runRouteLookup and by nothing else.
  const [routeAsk, setRouteAsk] = useState<RouteAsk | null>(null);

  // ── THE SHEET, BETWEEN THE MAP SCREEN AND THE SHELL ───────────────────────
  //
  // WHETHER IT IS UP, WHETHER IT IS ON ITS WAY DOWN, AND AT WHICH DETENT. The
  // map screen presents by setting sheetPresented, which mounts the shell, and
  // asks to dismiss by setting sheetClosing; the shell springs down and, when
  // it has landed, clears both. A drag off the bottom sets sheetClosing from
  // inside the shell and ends the same way. The detent is written by the shell
  // on every release and read by the map screen for its bubble's floor.
  const [sheetPresented, setSheetPresented] = useState(false);
  const [sheetClosing, setSheetClosing] = useState(false);
  const [sheetDetent, setSheetDetent] = useState(0);
  // THE SHEET'S HEIGHTS ON THIS DEVICE, from the window and the tab bar's
  // inset -- this provider is inside the tab, so its bottom inset IS the bar's.
  // Hooks, not Dimensions.get, so rotation re-derives them. The shell springs
  // between these and the map screen's bubble clears them.
  const { height: sheetWinHeight, width: sheetWinWidth } = useWindowDimensions();
  const sheetInsets = useSafeAreaInsets();
  // sheetHeights is computed below routeNotes, whose lines the small detent
  // has to include.

  // THE HOST'S `loading`, FOR THE SHEET'S PICKERS. A date pick or an end pick
  // must not fire a second fetch over one in flight, and the flag that says so
  // is the host's. Read through the ref so the sheet needs nothing bound.
  const hostLoading = () => host.current?.loading ?? false;

  // `ask` is what the sentence asked beyond the route -- see RouteAsk -- and
  // only the model rung passes one. Every other caller clears it by omission.
  const runRouteLookup = async (
    origin: string, destination: string, day: string | null, ask: RouteAsk | null = null,
  ) => {
    const h = host.current;
    setRouteAsk(ask);
    // Connections belong to the board they were searched from; a new board
    // starts without them.
    cancelConnections();
    h?.setError("");
    h?.setSaveError("");
    // The three result kinds are mutually exclusive; a route answer replaces
    // whatever was on screen.
    h?.setFlight(null);
    h?.setChatResponse(null);
    h?.setFlightRecord(null);
    setRouteResult(null);
    h?.setLoading(true);
    try {
      // The date is omitted entirely for Today, not sent empty: the backend
      // treats absent and empty alike, but omitting keeps the URL identical to
      // what it has always been.
      const query = day === null
        ? `hours=${ROUTE_TODAY_HOURS}`
        : `hours=${ROUTE_TODAY_HOURS}&date=${day}`;
      const response = await fetch(`${API_BASE}/route/${origin}/${destination}?${query}`);
      const data = await response.json();

      // The envelope always carries an `error` key; non-null means failure.
      if (data.error || !response.ok) {
        h?.setError(data.error || "Something went wrong. Please try again.");
        h?.setErrorCounter(c => c + 1);
        return;
      }

      // Airline exclusions are keyed to one result set; a different route has a
      // different carrier list, so carrying them over would silently hide rows.
      setRouteAirlinesOff([]);
      setRouteResult(data as RouteResult);
      h?.showResult();
      // NO DIRECT FLIGHT: LOOK FOR CONNECTIONS WITHOUT BEING ASKED. The
      // unresolved rows count as possible directs until the device has checked
      // them, so a board with only those does not start a search.
      const r = data as RouteResult;
      if (r.flights.length === 0 && (r.unresolved ?? []).length === 0) {
        startConnections(origin, destination, day, true);
      }
    } catch {
      h?.setError("Could not reach the server. Please check your connection and try again.");
      h?.setErrorCounter(c => c + 1);
    } finally {
      h?.setLoading(false);
    }
  };

  // Bookmark on a route row: look the flight up, then save it, without the card
  // ever appearing. It deliberately does NOT reuse runFlightLookup, which sets
  // `flight` and calls showResult() — that would unmount the route list and flash
  // the card open and shut. Same endpoint, same DTO mapping, no card.
  //
  // Costs 2 units per distinct flight. The backend caches a successful lookup for
  // five minutes, so re-tapping the same number inside that window is free.
  const saveFromRoute = async (flightNumber: string, date: string | null,
                              origin: string | null = null) => {
    if (routeSavingKey !== null) return;      // one at a time; the UI also disables the rest
    const h = host.current;
    setRouteSavingKey(flightNumber);
    h?.setError("");
    try {
      // Same date AND same origin the row was rendered from. Without the date
      // this stored TODAY's instance of the flight under a row the user picked
      // off a future board; without the origin it stored whichever leg of a tag
      // flight the provider offered first. Both persist, which is what makes
      // them worse here than on the card.
      const response = await fetch(flightUrl(flightNumber, date, origin));
      const data = await response.json();

      if (data.error || !response.ok) {
        h?.setError(data.error || "Something went wrong. Please try again.");
        h?.setErrorCounter(c => c + 1);
        return;
      }

      const record = savedFlightFromApi(data);
      // THE WHOLE SAVE IS saveRecord's, the undo check included — the window
      // belongs to the flight, not to the control that closed it. What is left
      // here is this path's own wording for the three endings, which is the
      // error channel and a shake where the card raises a toast.
      const outcome = await saveRecord(record);
      if (outcome.kind === 'restored') { showToast('restored'); return; }
      if (outcome.kind === 'limit') {
        h?.setError('watchlist limit reached — unsave one first');
        h?.setErrorCounter(c => c + 1);
        return;
      }
      // Reminders on by default, exactly as the card's bookmark does it.
      showToast(SAVE_MSG[outcome.remind]);
    } catch {
      h?.setError("Could not reach the server. Please check your connection and try again.");
      h?.setErrorCounter(c => c + 1);
    } finally {
      setRouteSavingKey(null);
    }
  };

  // ── SAVING A CONNECTION: BOTH LEGS ────────────────────────────────────────
  //
  // EACH LEG LOOKED UP ON ITS OWN DAY FROM ITS OWN AIRPORT, exactly as a direct
  // row's save does, so a tag flight's other leg is never the one stored: 2
  // units a leg. Both lookups must succeed before anything is written; then
  // saveLegs writes both, or neither.
  //
  // `owned` false IS THE BOOKMARK: both legs watched, as a direct row's bookmark
  // watches one flight. true IS "ADD TO MY FLIGHTS" from the long press: both
  // legs as one owned trip. See saveLegs.
  const saveItinerary = async (o: RouteItinerary, owned: boolean) => {
    if (routeSavingKey !== null || routeResult === null) return;
    const h = host.current;
    const key = optKey(o);
    setRouteSavingKey(key);
    h?.setError("");
    try {
      const records = [];
      for (const { leg, origin } of optLegsWithOrigin(o, routeResult.origin)) {
        const response = await fetch(flightUrl(leg.flight_number, routeDayOf(leg), origin));
        const data = await response.json();
        if (data.error || !response.ok) {
          h?.setError(data.error || `Could not look up ${leg.flight_number}. Nothing was saved.`);
          h?.setErrorCounter(c => c + 1);
          return;
        }
        records.push(savedFlightFromApi(data));
      }
      const outcome = await saveLegs(records, owned);
      if (outcome.kind === 'limit') {
        h?.setError('watchlist limit reached. Nothing was saved -- unsave one first');
        h?.setErrorCounter(c => c + 1);
        return;
      }
      if (outcome.kind === 'saved') showToast((owned ? OWN_MSG : SAVE_MSG)[outcome.remind]);
    } catch {
      h?.setError("Could not reach the server. Nothing was saved.");
      h?.setErrorCounter(c => c + 1);
    } finally {
      setRouteSavingKey(null);
    }
  };

  // "REMOVE FROM MY FLIGHTS" FOR A CONNECTION: both legs back to watched, as the
  // card's own menu item does for one flight. Nothing is unsaved.
  const disownItinerary = async (o: RouteItinerary) => {
    for (const leg of o.legs) {
      const f = savedFlights.find(s => s.id === makeFlightId(leg.flight_number, routeDayOf(leg)));
      if (f !== undefined && f.tripId !== null) await disownFlight(f);
    }
  };

  // EVERY DERIVATION FROM HERE DOWN READS AN OPTION, THROUGH THE ACCESSORS. The
  // duration, the carrier and the two ends moved to module scope with the
  // union -- see optDurationMs, legCarrier, optDepIso -- because the row and the
  // bubble need them as well and neither can reach into this hook.
  const routeDepartureTs = (o: RouteOption): number => routeTs(optDepIso(o)) ?? NO_TIME;
  const routeArrivalTs = (o: RouteOption): number => routeTs(optArrIso(o)) ?? NO_TIME;

  // The hour as it reads AT THE AIRPORT, taken from the wall-clock digits.
  // new Date(iso).getHours() would report the device's zone instead, which puts
  // a Bengaluru breakfast flight in the evening band for a user in London.
  const routeHourOf = (iso: string | null): number | null => {
    const m = /T(\d{2}):/.exec(iso ?? '');
    return m ? Number(m[1]) : null;
  };

  // THE FIRST DEPARTURE AND THE LAST ARRIVAL, which on a direct option are the
  // row's own two clocks.
  const routeDepBand = (o: RouteOption): RouteBand | null => {
    const h = routeHourOf(optDepIso(o));
    return h === null ? null : bandForHour(h);
  };

  const routeArrBand = (o: RouteOption): RouteBand | null => {
    const h = routeHourOf(optArrIso(o));
    return h === null ? null : bandForHour(h);
  };

  // Rows the backend named but could not code, resolved here — where the
  // airport dataset lives — and kept only when the name resolves to the
  // destination that was actually searched for. The code is filled in from the
  // resolution, so from this point on a recovered row is indistinguishable from
  // a matched one and every consumer below needs no special case.
  //
  // A name that resolves to nothing, or to somewhere else, is dropped: there
  // would be no honest way to show it in a list of flights to one destination.
  const routeRecovered: RouteFlight[] = routeResult === null
    ? []
    : (routeResult.unresolved ?? []).flatMap(r => {
      const hit = routeResolveDestination(r.destination_airport);
      return hit !== null && hit.iata === routeResult.destination
        ? [{ ...r, destination_iata: hit.iata }]
        : [];
    });

  // THE row set. Everything below counts, filters, sorts and groups this, so a
  // recovered row is counted exactly once, in exactly one group, like any other.
  //
  // The fills are merged HERE and nowhere else, which is the whole reason this
  // is one line rather than a patch at the render site. An arrival time is not
  // only something the row prints: routeDurationMs reads it, so it decides the
  // duration sort, the arrival sort and which row wears the fastest marker.
  // Filling it in at the Text would leave a row showing a time while every
  // derivation above still treated it as having none — a row sorted last for
  // want of a value it is visibly displaying. Merging at the source means the
  // standing checks hold against exactly what is on screen.
  //
  // The visible consequence, and it is intended: a row that gains a time can
  // move, and can take the fastest marker, a moment after the list first
  // appears. That is the list becoming correct, not the list twitching.
  //
  // PER LEG, so a connection's second leg is filled by the same lookup a direct
  // row is. An option is built from filled legs, never filled afterwards, which
  // is what keeps the fill upstream of every derivation.
  const fillLeg = (r: RouteLeg): RouteLeg => {
    if (r.arrival_scheduled_iso !== null || r.arrival_scheduled !== null) return r;
    const fill = routeFills[makeFlightId(r.flight_number, routeDayOf(r))];
    return fill === undefined
      ? r
      : { ...r, arrival_scheduled: fill.text, arrival_scheduled_iso: fill.iso };
  };
  // DIRECTS ONLY, TODAY. The connection search will append its itineraries
  // here, each leg mapped through fillLeg, and nothing below this line will
  // have to change for them.
  // AND THE CONNECTIONS, WHEN THEY BELONG TO THIS BOARD. Each leg through
  // fillLeg like any other row, so everything below -- the sorts, the bands, the
  // catch deadlines, the airline filter -- treats a connection exactly as it
  // treats a direct flight. The key check stops a stream for a route the user
  // has left from adding rows to the one on screen.
  const routeConnShown: RouteItinerary[] = routeResult === null
    || routeConn.key !== connKey(routeResult.origin, routeResult.destination, routeResult.date)
    ? []
    : connItineraries<RouteFlight>(routeConn).map((w: WireItinerary<RouteFlight>) => ({
      kind: 'via' as const,
      legs: [fillLeg(w.legs[0]), fillLeg(w.legs[1])] as [RouteLeg, RouteLeg],
      hub: w.hub,
      overnight: w.overnight,
      international: w.international,
      transfer: w.transfer,
    }));
  const routeRows: RouteOption[] = routeResult === null
    ? []
    : [
      ...[...routeResult.flights, ...routeRecovered].map(r => ({ kind: 'direct' as const, leg: fillLeg(r) })),
      ...routeConnShown,
    ];

  // ── THE CLOCK THE BANDS ARE READ AGAINST ──────────────────────────────────
  //
  // A BAND IS A FACT ABOUT NOW, and a list left on screen crosses deadlines
  // while it sits there: at 18:29 a 20:00 domestic departure is catchable, at
  // 18:31 it is risky, at 19:01 it is gone. So `now` is state, and it advances
  // exactly when a band would change rather than on a metronome: the effect
  // finds the earliest deadline still ahead across every row and wakes then.
  // A minute tick would re-render the whole search tree sixty times an hour
  // to move nothing; this re-renders it once per boundary crossed.
  //
  // AND ON RESUME. A timer does not fire in the background, so a phone that
  // comes back after an hour reads the clock again on its own.
  //
  // THE DEPARTED FLAG DOES NOT MOVE WITH THIS CLOCK. It is the backend's and
  // arrives with the board; the closed deadline covers the gap, since a flight
  // is uncatchable an hour before it leaves whether or not it has left.
  const [catchNow, setCatchNow] = useState(() => Date.now());
  // Which result the clock was last read for. See the effect below.
  const catchReadFor = useRef<RouteResult | null>(null);
  // THE NEXT MOMENT ANY BAND CHANGES, or null when no deadline is still ahead.
  // Computed in render from the rows, so the effect below keys on one number
  // and not on an array rebuilt every render.
  const catchNext = routeResult === null
    ? null
    : routeRows.reduce<number | null>((next, o) => {
      const b = optCatchBoundaries(o, routeResult.origin, routeResult.destination);
      if (b === null) return next;
      for (const t of [b.risky, b.closed]) {
        if (t > catchNow && (next === null || t < next)) next = t;
      }
      return next;
    }, null);
  useEffect(() => {
    if (routeResult === null) return;
    const sub = AppState.addEventListener('change', s => { if (s === 'active') setCatchNow(Date.now()); });
    // A NEW RESULT READS THE CLOCK AFRESH, on the next tick, so a search run
    // after the phone sat idle does not paint its bands from the last search's
    // clock. Next tick rather than now: a render has to stay pure, and a state
    // set inside an effect cascades a render, so neither may read the clock.
    let fresh: ReturnType<typeof setTimeout> | null = null;
    if (catchReadFor.current !== routeResult) {
      catchReadFor.current = routeResult;
      fresh = setTimeout(() => setCatchNow(Date.now()), 0);
    }
    // A beat past the boundary, so the read lands on the far side of it. The
    // wait is measured from the real clock, not from catchNow, which may be a
    // render or two old by the time this runs.
    const next = catchNext === null
      ? null
      : setTimeout(() => setCatchNow(Date.now()), Math.max(0, catchNext - Date.now()) + 250);
    return () => {
      if (fresh !== null) clearTimeout(fresh);
      if (next !== null) clearTimeout(next);
      sub.remove();
    };
  }, [routeResult, catchNext]);

  const routeCatchOf = (o: RouteOption): RouteCatch =>
    routeResult === null ? 'catchable' : optCatch(o, routeResult.origin, routeResult.destination, catchNow);

  // AFTER the list is on screen, never before it.
  //
  // The effect runs on commit, so the rows are already rendered with their
  // dashes and nothing is held up waiting for a network call. Each answer
  // arrives as its own setState and swaps one row's dash for a time in place.
  //
  // Keyed on number AND date, so a dated search fills the instance it is
  // actually showing, and a flight looked up once is never looked up again this
  // session — routeFillTried is a ref, so it outlives every re-render and every
  // new search. The key goes in BEFORE the request rather than after it, which
  // is what makes a failure final: a row whose fetch fails keeps its dash, and
  // nothing retries it. No error is surfaced either. The list was already
  // telling the truth; this only ever improves on it.
  //
  // LEGS, NOT OPTIONS, AND ROUTE_FILL_MAX COUNTS LEGS. A connection is two
  // lookups if both its legs came without an arrival, and the cap is on what is
  // spent rather than on what is listed. A leg shared by two options is one key
  // and one lookup.
  useEffect(() => {
    if (routeResult === null) return;
    const targets: { leg: RouteLeg; origin: string }[] = [];
    outer: for (const o of routeRows) {
      for (const { leg, origin } of optLegsWithOrigin(o, routeResult.origin)) {
        // Already has one. Nothing to buy.
        if (leg.arrival_scheduled_iso !== null || leg.arrival_scheduled !== null) continue;
        if (routeFillTried.current.has(makeFlightId(leg.flight_number, routeDayOf(leg)))) continue;
        targets.push({ leg, origin });
        if (targets.length === ROUTE_FILL_MAX) break outer;
      }
    }
    if (targets.length === 0) return;

    let cancelled = false;
    (async () => {
      // One at a time. Three parallel requests would arrive as three renders in
      // the same frame anyway, and serialising keeps the burst off the backend.
      for (const { leg: r, origin } of targets) {
        if (cancelled) return;
        const day = routeDayOf(r);
        const key = makeFlightId(r.flight_number, day);
        routeFillTried.current.add(key);
        try {
          // THE LEG'S OWN ORIGIN: the board's for a direct row and a first leg,
          // the hub's for a second. Without it a tag flight fills this row with
          // the other leg's arrival time — a wrong number in a cell that looks
          // exactly like a right one. See optLegsWithOrigin.
          const res = await fetch(flightUrl(r.flight_number, day, origin));
          const data = await res.json();
          if (!res.ok || data.error) continue;
          const text = data.arrival_scheduled ?? null;
          const iso = data.arrival_scheduled_iso ?? null;
          // The endpoint answered but has no arrival either. Nothing to write,
          // and the key is already spent, so this settles the row for good.
          if (text === null && iso === null) continue;
          if (cancelled) return;
          setRouteFills(prev => ({ ...prev, [key]: { text, iso } }));
        } catch {
          // Quiet on purpose. The row keeps its dash.
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeResult]);

  // What the envelope's own totals become once recoveries are included. The
  // backend's count and total_found describe `flights` alone, by design.
  const routeShown = routeRows.length;
  const routeFound = routeResult === null
    ? 0
    : routeResult.total_found + routeRecovered.length;

  // Only carriers actually present in this result set.
  const routeAirlineOptions = routeResult
    ? Array.from(new Set(routeRows.flatMap(optCarriers))).sort()
    : [];

  // THE OPTION'S KEY, under the name every consumer already reads. See optKey.
  const routeRowKey = optKey;

  // Missing values resolve to NO_TIME in every mode, so unparseable rows sort
  // last whichever key is active.
  // ASCENDING ALWAYS, so a reversed ordering is a negated key rather than a
  // second comparator. NO_TIME is the sentinel a row with no readable time
  // takes, and negating it would promote exactly those rows to the top of the
  // latest list -- so an unreadable row keeps the sentinel and stays last.
  const routeSortKey = (o: RouteOption): number =>
    routeSort === 'arrival' ? routeArrivalTs(o)
      : routeSort === 'duration' ? (optDurationMs(o) ?? NO_TIME)
        : routeSort === 'latest'
          ? (routeDepartureTs(o) === NO_TIME ? NO_TIME : -routeDepartureTs(o))
          : routeDepartureTs(o);

  // BY CARRIER, THEN BY THE CLOCK. Sorting on a name alone leaves one airline's
  // flights in whatever order the provider sent them, which reads as no order at
  // all. The comparator below is the only one that is not a single number, so it
  // is applied separately -- see routeSorted.
  //
  // THE FIRST LEG'S CARRIER, on a connection. A journey is filed under the
  // airline that flies it out, which is also how a person looks for it.
  const routeAirlineOf = (o: RouteOption): string => {
    const first = optFirst(o);
    return airlineFromFlightNumber(first.flight_number) ?? first.flight_number.slice(0, 2);
  };

  // One predicate for both the real filter and the option counts, so a count can
  // never disagree with what enabling the option actually produces. `skip` names
  // the dimension to ignore.
  //
  // A row whose band cannot be determined is never hidden by that filter: the
  // app has no grounds to place it in a band, and hiding data it cannot classify
  // is worse than showing it.
  //
  // THE AIRLINE FILTER HIDES AN OPTION WHEN ANY OF ITS CARRIERS IS OFF. Turning
  // IndiGo off and still seeing an IndiGo leg on screen would read as the filter
  // not working; the other reading -- hidden only when every carrier is off --
  // is the one nobody expects. On a direct row the two readings are the same.
  const routePasses = (o: RouteOption, skip: 'dep' | 'arr' | 'air' | null) => {
    if (skip !== 'dep') {
      const b = routeDepBand(o);
      if (b !== null && !routeDepBands[b]) return false;
    }
    if (skip !== 'arr') {
      const b = routeArrBand(o);
      if (b !== null && !routeArrBands[b]) return false;
    }
    if (skip !== 'air' && optCarriers(o).some(c => routeAirlinesOff.includes(c))) return false;
    return true;
  };

  const routeVisible = routeResult
    ? routeRows.filter(o => routePasses(o, null))
    : [];

  // Counted with the OTHER filters applied but not this one, so the number says
  // what enabling the option would give you — and does not collapse to zero the
  // moment you switch the option off.
  //
  // keysOf RETURNS A LIST, because an option can count under more than one
  // key: a connection counts under each of its carriers, so the number beside
  // a carrier says what switching it on would show. A band is one key or none.
  const routeCountBy = (skip: 'dep' | 'arr' | 'air', keysOf: (o: RouteOption) => string[]) => {
    const out: Record<string, number> = {};
    for (const o of routeRows) {
      if (!routePasses(o, skip)) continue;
      for (const k of keysOf(o)) out[k] = (out[k] ?? 0) + 1;
    }
    return out;
  };
  const bandKeys = (b: RouteBand | null): string[] => (b === null ? [] : [b]);
  const routeDepCounts = routeCountBy('dep', o => bandKeys(routeDepBand(o)));
  const routeArrCounts = routeCountBy('arr', o => bandKeys(routeArrBand(o)));
  const routeAirCounts = routeCountBy('air', optCarriers);

  const sortRows = (rows: RouteOption[]): RouteOption[] => routeSort === 'airline'
    ? [...rows].sort((a, b) => {
      const n = routeAirlineOf(a).localeCompare(routeAirlineOf(b));
      return n !== 0 ? n : routeDepartureTs(a) - routeDepartureTs(b);
    })
    : [...rows].sort((a, b) => routeSortKey(a) - routeSortKey(b));

  // TWO GROUPS, EACH IN THE CHOSEN ORDER, AFTER THE FILTERS. The filters have
  // already applied to routeVisible, so they narrow both groups alike and the
  // counts on the pills go on describing the whole board. What splits the
  // groups is only whether the flight can still be caught -- see optCatch.
  //
  // routeSorted IS THE OPEN GROUP, under the name every reader already has,
  // and the fastest marker, the pin and the bubble's default all derive from
  // it: a flight nobody can board is never the fastest way to get anywhere.
  // routeClosedSorted is drawn below it under its own heading.
  const routeSorted = sortRows(routeVisible.filter(o => routeCatchOf(o) !== 'uncatchable'));
  const routeClosedSorted = sortRows(routeVisible.filter(o => routeCatchOf(o) === 'uncatchable'));
  const routeHiddenCount = routeRows.length - routeVisible.length;

  // Computed over the FILTERED set, so the marker always describes what is
  // currently on screen. Null when fewer than two rows are timed — one row has
  // nothing to be faster than — or when every duration is identical, where
  // "fastest" would describe the whole list and so describe nothing.
  //
  // A TIE no longer suppresses it. Ties are ordinary: five rows share 170m on a
  // typical BLR-DEL board, and a tie on the minimum used to blank the marker
  // outright — measured at 24% of two-row and 16% of three-row filtered subsets.
  // Rows sharing the shortest time are genuinely the best available, so every
  // one of them keeps its in-row tag and the first in the CURRENT sort order
  // takes the pin. `timed` is built from routeSorted, so "first" means first as
  // rendered, and the pin cannot jump between renders.
  // A CONNECTION MAY BE THE FASTEST ONLY WHEN ITS SEARCH FINISHED COMPLETE. While
  // hubs are still loading, or when the guard stopped the search, an unfetched
  // hub-day could hold something faster, so only direct flights compete.
  const connMayWin = connFastestAllowed(routeConn);
  const routeFastest = (() => {
    const timed = routeSorted
      .filter(o => o.kind === 'direct' || connMayWin)
      .map(o => ({ key: routeRowKey(o), ms: optDurationMs(o) }))
      .filter((v): v is { key: string; ms: number } => v.ms !== null);
    if (timed.length < 2) return null;
    const min = Math.min(...timed.map(v => v.ms));
    if (min === Math.max(...timed.map(v => v.ms))) return null;
    const keys = timed.filter(v => v.ms === min).map(v => v.key);
    return { keys: new Set(keys), pin: keys[0] };
  })();

  // Every row achieving the shortest time carries the tag; exactly one of them
  // is lifted into the pin.
  const routeFastestKeys = routeFastest?.keys ?? new Set<string>();
  const routeFastestKey = routeFastest?.pin ?? null;

  // Lifted OUT of the list and pinned above it, so it appears exactly once
  // rather than twice. Never under a duration sort: it is already the first row
  // there, and pinning would buy a heading and a duplicate.
  const routePinned = routeSort !== 'duration' && routeFastestKey !== null
    ? routeSorted.find(r => routeRowKey(r) === routeFastestKey) ?? null
    : null;

  // Everything the list below renders. The groups and their counts both derive
  // from this, so a heading can never claim a row that was lifted out.
  const routeListed = routePinned === null
    ? routeSorted
    : routeSorted.filter(r => routeRowKey(r) !== routeFastestKey);

  // WHICH ROW IS ACTUALLY LAST, as a key rather than an index.
  //
  // routeRowKey rather than object identity, because the row objects are rebuilt
  // by every derivation above and identity does not survive that.
  //
  // THE END OF WHAT IS DRAWN, NOT OF routeListed. The sheet draws the open
  // group flat with nothing lifted out of it, then the closed group under its
  // heading, so the last row drawn is the last of the closed group when there
  // is one and the last of the open group otherwise. routePinned and
  // routeListed stay for the bubble's default selection, which still prefers
  // the fastest.
  const routeDrawnLast = routeClosedSorted.length > 0
    ? routeClosedSorted[routeClosedSorted.length - 1]
    : routeSorted.length > 0 ? routeSorted[routeSorted.length - 1] : null;
  const routeLastKey = routeDrawnLast === null ? null : routeRowKey(routeDrawnLast);

  // ── WHICH FLIGHT THE BUBBLE IS SHOWING ────────────────────────────────────
  //
  // A KEY RATHER THAN A ROW, because the rows are rebuilt on every filter and
  // sort change and holding one would pin a stale object. The key survives all
  // of that and resolves to whatever the current list says it is.
  //
  // NULL MEANS THE DEFAULT, AND THE DEFAULT IS THE FASTEST. Not the first row:
  // the first row depends on the ordering, so the bubble would change flights
  // when somebody sorted, which is not what sorting means.
  //
  // THE CLOSED GROUP IS SELECTABLE, AND LAST. A tap on a departed flight draws
  // its arc like any other -- that is how somebody follows a flight they are
  // not on -- but the default never lands there while an open row exists.
  const routeSelected = (() => {
    const all = [
      ...(routePinned === null ? [] : [routePinned]),
      ...routeListed,
      ...routeClosedSorted,
    ];
    if (all.length === 0) return null;
    if (routeSelectedKey !== null) {
      const hit = all.find(r => routeRowKey(r) === routeSelectedKey);
      if (hit !== undefined) return hit;
    }
    const fastest = routeFastestKey === null
      ? undefined
      : all.find(r => routeRowKey(r) === routeFastestKey);
    return fastest ?? all[0] ?? null;
  })();

  // THE WORD FOR WHY THIS ONE, AND IT DESCRIBES THE SELECTED FLIGHT OR SAYS
  // NOTHING. The list computes one distinction of its own -- which rows are
  // fastest -- so that is said when the selected flight is one of them. Failing
  // that, the ordering the person chose is an honest answer only for the row
  // it put on top: "Earliest" beside the third-earliest flight is a claim the
  // flight does not meet, and under the Fastest ordering the label IS
  // "Fastest", which is exactly the word this must not print for a slower
  // flight somebody tapped. A flight that is neither fastest nor first gets
  // no word: the times and codes beside it say what it is, and the person
  // chose it, which needs no explaining.
  //
  // By airline is never a reason. Being first under it means having the
  // alphabetically first carrier, which is not a fact about the flight.
  const routeReason = (() => {
    if (routeSelected === null) return '';
    const key = routeRowKey(routeSelected);
    if (routeFastestKeys.has(key) || key === routeFastestKey) return 'Fastest';
    if (routeSort === 'duration' || routeSort === 'airline') return '';
    const first = routeSorted[0];
    return first !== undefined && routeRowKey(first) === key ? ROUTE_SORT_LABELS[routeSort] : '';
  })();

  const routeSelectedDur = routeSelected === null ? null : optDurationMs(routeSelected);

  // Which filters are actually narrowing the list, for the all-hidden message.
  const routeActiveFilters = [
    ROUTE_BANDS.every(b => routeDepBands[b]) ? null : 'departure time',
    ROUTE_BANDS.every(b => routeArrBands[b]) ? null : 'arrival time',
    routeAirlinesOff.length === 0 ? null : 'airline',
  ].filter((v): v is string => v !== null);

  // Everything-on for the filters, and sort back to its default.
  const routeFiltersDirty =
    !ROUTE_BANDS.every(b => routeDepBands[b])
    || !ROUTE_BANDS.every(b => routeArrBands[b])
    || routeAirlinesOff.length > 0;

  const routeAirOn = routeAirlineOptions.filter(a => !routeAirlinesOff.includes(a));

  const routeControlsDirty =
    routeFiltersDirty || routeSort !== ROUTE_SORT_DEFAULT || routeDate !== null;

  // ── THE LINE UNDER THE PILL ───────────────────────────────────────────────
  //
  // A QUESTION IS ANSWERED FROM THE BOARD, ON THE DEVICE, from the same rows
  // and the same filters the list draws, so the answer and the list cannot
  // disagree. Each shape reads one row: the extreme of the OPEN group under the
  // key the question names. Not routeSorted[0], because the person may re-sort
  // the list afterwards and "next" has to go on meaning next; and the open
  // group, never the closed one, because a flight nobody can board is not the
  // next flight anywhere.
  //
  // NEVER SILENT. A board with nothing to answer from says so in the same
  // line. An origin the app assumed and a range it cut are said whether or not
  // there was a question, because both are things the person did not type.
  const routeNotes: string[] = (() => {
    if (routeAsk === null || routeResult === null) return [];
    const out: string[] = [];
    const cityOf = (iata: string) => airportByCode(iata)?.city ?? iata;
    const fromCity = cityOf(routeResult.origin);
    const toCity = cityOf(routeResult.destination);
    // The board's own span, in words: a dated board is its day, the rolling
    // one is its window, which may run past midnight and so is not "today".
    const when = routeResult.date === null
      ? `in the next ${routeResult.window_hours} hours`
      : `on ${routeDateLabel(routeResult.date)}`;
    const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
    const open = routeVisible.filter(o => routeCatchOf(o) !== 'uncatchable');
    // The row at the extreme of a key, skipping rows the key cannot place.
    const extreme = (
      rows: RouteOption[], key: (o: RouteOption) => number, largest = false,
    ): RouteOption | null => {
      let best: RouteOption | null = null;
      let bestKey = 0;
      for (const o of rows) {
        const k = key(o);
        if (k === NO_TIME) continue;
        if (best === null || (largest ? k > bestKey : k < bestKey)) { best = o; bestKey = k; }
      }
      return best;
    };
    // THE CLOCK IN WORDS, WITH ITS ZONE, and the phone's time in brackets
    // where the two differ: "at 14:20 IST (02:50 your time) from Delhi".
    const describe = (o: RouteOption): string => {
      const leg = optFirst(o);
      const from = legOrigin(leg, routeResult.origin);
      const z = boardClock(leg.departure_scheduled_iso, leg.departure_scheduled, from);
      return `${legCarrier(leg)} ${leg.flight_number} at ${clockInWords(z)} from ${cityOf(from)}`;
    };
    const q = routeAsk.question;
    if (q !== null) {
      if (routeShown === 0) {
        out.push(`No flights from ${fromCity} to ${toCity} ${when}`);
      } else if (q === 'count') {
        out.push(`${plural(routeShown, 'flight')} from ${fromCity} to ${toCity} ${when}`
          + (open.length < routeShown ? `, ${open.length} still to catch` : ''));
      } else if (q === 'airlines') {
        const names = Array.from(new Set(routeRows.flatMap(optCarriers))).sort();
        out.push(`${plural(names.length, 'airline')} ${names.length === 1 ? 'flies' : 'fly'} `
          + `${fromCity} to ${toCity}: ${names.join(', ')}`);
      } else if (routeVisible.length === 0) {
        out.push('Every flight is hidden by a filter');
      } else if (open.length === 0) {
        out.push(`No more flights to ${toCity} ${when} can be caught`);
      } else if (q === 'next' || q === 'first') {
        const o = extreme(open, routeDepartureTs);
        out.push(o === null
          ? `No timed flight to ${toCity} ${when}`
          : q === 'next'
            ? `Next flight to ${toCity} is ${describe(o)}`
            : `First flight to ${toCity} ${when} is ${describe(o)}`);
      } else if (q === 'last') {
        const o = extreme(open, routeDepartureTs, true);
        out.push(o === null
          ? `No timed flight to ${toCity} ${when}`
          : `Last flight to ${toCity} ${when} is ${describe(o)}`);
      } else if (q === 'fastest') {
        const o = extreme(open, x => optDurationMs(x) ?? NO_TIME);
        out.push(o === null
          ? `No flight to ${toCity} ${when} has a known duration`
          : `Fastest flight to ${toCity} is ${describe(o)}, ${routeDurLabel(optDurationMs(o))}`);
      } else {
        const o = extreme(open, routeArrivalTs);
        if (o === null) {
          out.push(`No flight to ${toCity} ${when} has a known arrival time`);
        } else {
          const last = optLast(o);
          const z = boardClock(last.arrival_scheduled_iso, last.arrival_scheduled ?? ROUTE_NO_TIME,
            last.destination_iata ?? routeResult.destination);
          out.push(`Earliest arrival in ${toCity} is ${clockInWords(z)}, ` + describe(o));
        }
      }
    }
    if (routeAsk.assumedOrigin !== null) {
      out.push(`From ${cityOf(routeAsk.assumedOrigin)}, assumed from your location`);
    }
    if (routeAsk.rangeLabel !== null && routeResult.date !== null) {
      out.push(`Searching ${routeDateLabel(routeResult.date)}, the first day of ${routeAsk.rangeLabel}`);
    }
    return out;
  })();

  // THE SMALL DETENT, WITH THE NOTES' LINES IN IT. See SHEET_NOTE_LINE.
  const noteChars = Math.max(20, Math.floor((sheetWinWidth - SHEET_SIDE_PAD * 2) / SHEET_NOTE_CHAR));
  const noteLines = routeNotes.reduce(
    (n, t) => n + Math.min(SHEET_NOTE_MAX_LINES, Math.max(1, Math.ceil(t.length / noteChars))), 0);
  const noteHeight = routeNotes.length === 0 ? 0 : SHEET_NOTE_GAP + noteLines * SHEET_NOTE_LINE;
  const sheetHeights = sheetDetents(sheetWinHeight, sheetInsets.bottom, SHEET_SMALL_HEIGHT + noteHeight);

  // The view-control half of a reset, without the re-fetch. Both search paths
  // call it so that "a search typed from scratch starts clean" is one rule in
  // one place rather than two lists that drift.
  const routeResetControls_forSearch = () => {
    setRouteDepBands(ALL_BANDS_ON);
    setRouteArrBands(ALL_BANDS_ON);
    setRouteSort(ROUTE_SORT_DEFAULT);
  };

  // Clears the view controls AND the date. The view half is free; the date half
  // is not, because a dated list has to be re-fetched for today to match the
  // control that now says Today.
  //
  // Tested on routeResult.date, not routeDate: it is the list on screen that
  // decides whether a fetch is owed. Already-today costs nothing, and a search
  // in flight is left alone.
  //
  // THE ANCHORED PANEL IS NOT CLOSED FROM HERE. That panel is the screen's, so
  // the screen closes it and then calls this. See routeResetControls there.
  const resetRouteControls = () => {
    setRouteDepBands(ALL_BANDS_ON);
    setRouteArrBands(ALL_BANDS_ON);
    setRouteAirlinesOff([]);
    setRouteSort(ROUTE_SORT_DEFAULT);
    setRouteDate(null);
    if (host.current?.loading) return;
    if (routeResult === null || routeResult.date === null) return;
    runRouteLookup(routeResult.origin, routeResult.destination, null);
  };

  return {
    bindHost,
    savedFlights,
    routeResult, setRouteResult,
    routeAsk, routeNotes,
    routeDate, setRouteDate,
    routeSort, setRouteSort,
    routeDepBands, setRouteDepBands,
    routeArrBands, setRouteArrBands,
    routeAirlinesOff, setRouteAirlinesOff,
    routePick, setRoutePick,
    routeSavingKey,
    routeConn, routeConnShown, startConnections, cancelConnections, saveItinerary, disownItinerary,
    routeSelectedKey, setRouteSelectedKey,
    runRouteLookup,
    saveFromRoute,
    // routeDurationMs LEFT THIS LIST. It is optDurationMs at module scope now,
    // imported by the row directly, because a duration is a fact about an
    // option and not about this hook's state.
    routeRowKey,
    routeShown, routeFound, routeHiddenCount,
    routeClosedSorted, routeCatchOf,
    routeAirlineOptions, routeAirOn,
    routeDepCounts, routeArrCounts, routeAirCounts,
    routeSorted, routeListed, routePinned,
    routeFastestKeys, routeLastKey,
    routeSelected, routeReason, routeSelectedDur,
    routeActiveFilters, routeFiltersDirty, routeControlsDirty,
    routeResetControls_forSearch, resetRouteControls,
    sheetPresented, setSheetPresented,
    sheetClosing, setSheetClosing,
    sheetDetent, setSheetDetent,
    sheetHeights,
    hostLoading,
  };
}

type RouteResultsValue = ReturnType<typeof useRouteResultsState>;

const RouteResultsContext = createContext<RouteResultsValue | null>(null);

// MOUNTED IN app/(tabs)/search/_layout.tsx, above the search Stack, so the map
// screen and the results sheet are both inside it. Inside SavedProvider and
// ToastProvider by construction -- the root layout mounts those around every
// route -- which is what lets the save path here reach the store and the toasts.
export function RouteResultsProvider({ children }: { children: ReactNode }) {
  const value = useRouteResultsState();
  return <RouteResultsContext.Provider value={value}>{children}</RouteResultsContext.Provider>;
}

export function useRouteResults(): RouteResultsValue {
  const value = useContext(RouteResultsContext);
  if (value === null) {
    throw new Error('useRouteResults must be used inside RouteResultsProvider');
  }
  return value;
}
