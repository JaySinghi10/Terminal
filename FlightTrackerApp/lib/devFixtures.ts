// ── FAKE FLIGHTS, FOR SEEING WHAT A DISRUPTION LOOKS LIKE ───────────────────
//
// EVERY DISRUPTION RENDERING IN THIS APP WAS UNVERIFIED, and the reason is that
// the only way to see one was to wait for it. A cancelled leg, a diverted
// flight, a tight connection, a bag belt: each is drawn by code nobody has
// looked at on a real screen, because arranging the real event means booking a
// flight and hoping it goes wrong.
//
// SO THE RECORDS HERE ARE THE SAME SHAPE AS REAL ONES, and that is the whole
// design. They are SavedFlight and PendingLeg values written into the ordinary
// store, under the ordinary account key, read by the ordinary selectors and
// drawn by the ordinary components. Nothing anywhere branches on "is this a
// fixture" to render it differently -- if it did, the thing being verified
// would be the branch rather than the screen.
//
// THEY ARE EXCLUDED FROM EXACTLY THREE THINGS, and all three are network:
// the pull-to-refresh queue, the landing sweep and the watch backfill. See
// isDevFixture and its three call sites in lib/saved.tsx. A fake flight number
// asked of the provider would spend a unit to be told it does not exist, on
// every refresh, for as long as the fixture sat there.
//
// __DEV__ IS FALSE IN ANY RELEASE BUNDLE, so the control that calls this is
// compiled out and this module is unreachable from a shipped app. It is
// imported by the profile sheet and by the store's three guards, and the guards
// are cheap string tests that would be correct even if a fixture somehow
// existed in production.
import { makeFlightId, type SavedFlight, type SavedFlightEndpoint } from './storage';
import { makePendingId, type PendingLeg } from './pendingRules';

// ── HOW A FIXTURE IS RECOGNISED ─────────────────────────────────────────────
//
// THE FLIGHT NUMBER, because it is the one field that is on both a SavedFlight
// and a PendingLeg, is part of both ids, and survives every copy the store
// makes. ZZ is not an assigned IATA carrier code, so nothing real can collide
// with it; the number is also what a person sees on screen, which makes a
// fixture obvious rather than something to be caught out by.
export const DEV_PREFIX = 'ZZ9';

export function isDevFixture(f: { flightNumber?: string | null } | null | undefined): boolean {
  return (f?.flightNumber ?? '').toUpperCase().startsWith(DEV_PREFIX);
}

// ── TIME, WRITTEN THE WAY THE PROVIDER WRITES IT ────────────────────────────
//
// LOCAL WALL CLOCK WITH A TRUE OFFSET, never UTC: that is what every *Iso field
// on a real record carries, and zonedIsoToTs reads the digits and the offset
// together. A fixture in UTC would be silently hours out at every airport and
// would make the connection arithmetic look broken when it was not.
function zoned(ms: number, offsetMin: number): string {
  const d = new Date(ms + offsetMin * 60_000);
  const p = (n: number) => String(n).padStart(2, '0');
  const sign = offsetMin < 0 ? '-' : '+';
  const abs = Math.abs(offsetMin);
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`
    + `T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
    + `${sign}${p(Math.floor(abs / 60))}:${p(abs % 60)}`;
}

// The printed string beside the ISO one, in the provider's own format: a
// 12-hour clock with the airport's zone label. Several renderers fall back to
// this when they cannot parse the ISO, so a fixture that omitted it would
// exercise a path real data never takes.
function clockText(ms: number, offsetMin: number, tzLabel: string): string {
  const d = new Date(ms + offsetMin * 60_000);
  const h24 = d.getUTCHours();
  const h = h24 % 12 === 0 ? 12 : h24 % 12;
  const m = String(d.getUTCMinutes()).padStart(2, '0');
  return `${h}:${m} ${h24 < 12 ? 'AM' : 'PM'} ${tzLabel}`;
}

function dayOf(ms: number, offsetMin: number): string {
  return zoned(ms, offsetMin).slice(0, 10);
}

type Place = {
  iata: string; airport: string; city: string; short: string;
  tz: string; tzLabel: string; offset: number;
};

// FOUR REAL AIRPORTS, because the connection rule reads their COUNTRIES out of
// the shipped dataset and a made-up code would resolve to nothing -- which the
// rule treats as a border crossing, quietly turning every domestic fixture
// international. BOM, DEL and BLR are India; DXB is not, which is what puts a
// border in the middle of the three-leg trip below.
const BOM: Place = { iata: 'BOM', airport: 'Mumbai Chhatrapati Shivaji', city: 'Mumbai', short: 'Chhatrapati Shivaji', tz: 'Asia/Kolkata', tzLabel: 'IST', offset: 330 };
const DEL: Place = { iata: 'DEL', airport: 'Delhi Indira Gandhi', city: 'Delhi', short: 'Indira Gandhi', tz: 'Asia/Kolkata', tzLabel: 'IST', offset: 330 };
const BLR: Place = { iata: 'BLR', airport: 'Bengaluru Kempegowda', city: 'Bengaluru', short: 'Kempegowda', tz: 'Asia/Kolkata', tzLabel: 'IST', offset: 330 };
const DXB: Place = { iata: 'DXB', airport: 'Dubai International', city: 'Dubai', short: 'Dubai', tz: 'Asia/Dubai', tzLabel: 'GST', offset: 240 };

type EndArgs = {
  place: Place;
  scheduledMs: number;
  estimatedMs?: number | null;
  actualMs?: number | null;
  terminal?: string | null;
  gate?: string | null;
  baggage?: string | null;
};

// EVERY FIELD A REAL ENDPOINT HAS, including the ones that are usually null.
// An absent key and a null key are different to a spread, and a fixture missing
// one would be a record shape the store never produces.
function endpoint(a: EndArgs): SavedFlightEndpoint {
  const { place: p } = a;
  const delay = a.estimatedMs != null || a.actualMs != null
    ? Math.round((((a.actualMs ?? a.estimatedMs) as number) - a.scheduledMs) / 60_000)
    : null;
  return {
    iata: p.iata,
    airport: p.airport,
    city: p.city,
    shortName: p.short,
    terminal: a.terminal ?? null,
    gate: a.gate ?? null,
    scheduled: clockText(a.scheduledMs, p.offset, p.tzLabel),
    // 'N/A' RATHER THAN AN EMPTY STRING, which is what the backend's own
    // format_time emits for an absent value and what every reader expects.
    actual: a.actualMs != null ? clockText(a.actualMs, p.offset, p.tzLabel) : 'N/A',
    estimated: a.estimatedMs != null ? clockText(a.estimatedMs, p.offset, p.tzLabel) : 'N/A',
    delay,
    scheduledIso: zoned(a.scheduledMs, p.offset),
    estimatedIso: a.estimatedMs != null ? zoned(a.estimatedMs, p.offset) : null,
    actualIso: a.actualMs != null ? zoned(a.actualMs, p.offset) : null,
    timezone: p.tz,
    checkinDesk: null,
    baggage: a.baggage ?? null,
    actualSource: a.actualMs != null ? 'revised' : null,
    estimatedSource: a.estimatedMs != null ? 'revised' : null,
    runwayIso: null,
  };
}

type LegArgs = {
  number: string;
  from: EndArgs;
  to: EndArgs;
  status?: string;
  rawStatus?: string | null;
  tripId?: string | null;
  landedMs?: number | null;
};

function leg(a: LegArgs): SavedFlight {
  const now = Date.now();
  const date = dayOf(a.from.scheduledMs, a.from.place.offset);
  return {
    id: makeFlightId(a.number, date),
    flightNumber: a.number,
    airline: 'Terminal Test Air',
    flightDate: date,
    status: a.status ?? 'scheduled',
    from: endpoint(a.from),
    to: endpoint(a.to),
    aircraftModel: 'Airbus A320',
    aircraftRegistration: 'VT-ZZZ',
    savedAt: now,
    updatedAt: now,
    landedAt: a.landedMs ?? null,
    // THE AUTHORITATIVE LANDING, and it is the only thing that makes
    // effectiveStatus say 'landed' -- see its note on the one promotion. A
    // fixture that set status alone would be demoted back to 'active' and the
    // landed rendering would never appear.
    landedUtc: a.landedMs != null ? new Date(a.landedMs).toISOString().slice(0, 16) + 'Z' : null,
    landingSource: a.landedMs != null ? 'fr24' : null,
    landingCheck: a.landedMs != null ? 'landed' : null,
    landingCheckedAt: a.landedMs != null ? now : null,
    archivedAt: null,
    remindersSetAt: null,
    tripId: a.tripId ?? null,
    pnr: 'ZZFIX1',
    operatingFlightNumber: null,
    operatedBy: null,
    rawStatus: a.rawStatus ?? 'Expected',
    // THE CURRENT VERSION, so normalizeRecord leaves these alone rather than
    // running a migration over them on the first read.
    schemaVersion: 13,
  };
}

const MIN = 60_000;
const HOUR = 60 * MIN;

// ── THE THREE-LEG TRIP EVERY SCENARIO IS BUILT FROM ─────────────────────────
//
// BOM -> DEL -> BLR -> DXB, which puts BOTH minimum connection times on one
// screen: the wait at DEL is between two domestic legs and takes the sixty
// minute minimum, and the wait at BLR feeds a leg that crosses a border and
// takes the hundred and twenty. A trip that was domestic throughout would
// leave half the rule undrawn.
//
// ANCHORED TO NOW rather than to fixed dates, so a fixture installed today is
// still ahead of the clock tomorrow. A fixed date would archive itself six
// hours after its arrival and vanish from the screen it exists to fill.
function tripLegs(tripId: string, opts: { leg2ArrivesAt?: number | null; leg1Status?: string; leg2Status?: string } = {}): SavedFlight[] {
  const t = Date.now();
  const l1Dep = t + 2 * HOUR, l1Arr = t + 4 * HOUR;
  const l2Dep = t + 7 * HOUR, l2Arr = t + 9.5 * HOUR;
  const l3Dep = t + 14 * HOUR, l3Arr = t + 18 * HOUR;
  return [
    leg({
      number: 'ZZ901', tripId,
      from: { place: BOM, scheduledMs: l1Dep, terminal: '2', gate: 'A7' },
      to: { place: DEL, scheduledMs: l1Arr, terminal: '3' },
      status: opts.leg1Status ?? 'scheduled',
      rawStatus: opts.leg1Status === 'cancelled' ? 'Canceled' : 'Expected',
    }),
    leg({
      number: 'ZZ902', tripId,
      from: { place: DEL, scheduledMs: l2Dep, terminal: '3', gate: 'B12' },
      to: {
        place: BLR, scheduledMs: l2Arr, terminal: '1',
        // THE DELAY LIVES ON THE ESTIMATE, which is where a real one lives:
        // the schedule never moves and the revised time is what the connection
        // arithmetic reads. See connectionRisk.
        estimatedMs: opts.leg2ArrivesAt ?? null,
      },
      status: opts.leg2Status ?? 'scheduled',
      rawStatus: opts.leg2Status === 'diverted' ? 'Diverted'
        : opts.leg2ArrivesAt != null ? 'Delayed' : 'Expected',
    }),
    leg({
      number: 'ZZ903', tripId,
      from: { place: BLR, scheduledMs: l3Dep, terminal: '1', gate: 'C3' },
      to: { place: DXB, scheduledMs: l3Arr, terminal: '3' },
    }),
  ];
}

export type DevScenario = {
  key: string;
  label: string;
  // What it is for, shown under the button so the menu explains itself.
  note: string;
  build: () => { flights: SavedFlight[]; pending: PendingLeg[] };
};

// THE TRIP ID IS STABLE WITHIN ONE INSTALL and different between them, so
// installing a second scenario replaces the first rather than joining it.
const tripId = () => `dev-${Date.now()}`;

function doubtLeg(): PendingLeg {
  const t = Date.now();
  const date = dayOf(t + 30 * HOUR, DEL.offset);
  return {
    id: makePendingId('ZZ906', date),
    flightNumber: 'ZZ906',
    operatingFlightNumber: null,
    date,
    origin: 'DEL',
    originName: 'Delhi Indira Gandhi',
    destination: 'BOM',
    destinationName: 'Mumbai Chhatrapati Shivaji',
    pnr: 'ZZFIX2',
    airline: 'Terminal Test Air',
    departureTime: '18:40',
    source: { subject: 'Your booking has been cancelled', received: new Date(t).toUTCString() },
    addedAt: t,
    lastTriedAt: t - 2 * HOUR,
    tries: 3,
    tripId: null,
    legStatus: 'scheduled',
    // THE WHOLE POINT OF THIS ONE: the airline cancelled the booking and named
    // no flight, so the leg is in doubt rather than cancelled. See
    // bookingCancelled in pendingRules.
    bookingCancelled: true,
    arrivalTime: '20:55',
    arrivalDate: null,
  };
}

export const DEV_SCENARIOS: DevScenario[] = [
  {
    key: 'trip-ok',
    label: 'Trip · all comfortable',
    note: 'Three legs, both connections clear. Nothing should be coloured.',
    build: () => ({ flights: tripLegs(tripId()), pending: [] }),
  },
  {
    key: 'trip-risk',
    label: 'Trip · connection at risk',
    note: 'Leg 2 lands late enough to leave about 2h15m for an international connection.',
    // Leg 3 departs at T+14h; an arrival at T+11h45m leaves 135 minutes, which
    // is inside the international minimum plus its cushion.
    build: () => ({ flights: tripLegs(tripId(), { leg2ArrivesAt: Date.now() + 11.75 * HOUR }), pending: [] }),
  },
  {
    key: 'trip-miss',
    label: 'Trip · connection missed',
    note: 'Leg 2 lands late enough to leave an hour, under the international minimum.',
    build: () => ({ flights: tripLegs(tripId(), { leg2ArrivesAt: Date.now() + 13 * HOUR }), pending: [] }),
  },
  {
    key: 'leg1-cancelled',
    label: 'Trip · leg 1 cancelled',
    note: 'The first leg is off. The card drops to the scheduled departure alone.',
    build: () => ({ flights: tripLegs(tripId(), { leg1Status: 'cancelled' }), pending: [] }),
  },
  {
    key: 'leg2-diverted',
    label: 'Trip · leg 2 diverted',
    note: 'The middle leg is diverted. Its destination and the arrow disappear.',
    build: () => ({ flights: tripLegs(tripId(), { leg2Status: 'diverted' }), pending: [] }),
  },
  {
    key: 'booking-doubt',
    label: 'Booking cancelled, legs unknown',
    note: 'A pending leg whose booking the airline cancelled without naming a flight.',
    build: () => ({ flights: [], pending: [doubtLeg()] }),
  },
  {
    key: 'in-air',
    label: 'In the air',
    note: 'Departed an hour ago, an hour to run. Draws the progress bar.',
    build: () => {
      const t = Date.now();
      return {
        flights: [leg({
          number: 'ZZ907',
          from: { place: BOM, scheduledMs: t - 65 * MIN, actualMs: t - 60 * MIN, terminal: '2', gate: 'A7' },
          to: { place: DEL, scheduledMs: t + 55 * MIN, estimatedMs: t + 60 * MIN, terminal: '3' },
          status: 'active',
          rawStatus: 'EnRoute',
        })],
        pending: [],
      };
    },
  },
  {
    key: 'landed-belt',
    label: 'Landed, bags on a belt',
    note: 'Touched down twenty minutes ago with a belt number.',
    build: () => {
      const t = Date.now();
      return {
        flights: [leg({
          number: 'ZZ908',
          from: { place: DEL, scheduledMs: t - 3 * HOUR, actualMs: t - 3 * HOUR, terminal: '3' },
          to: {
            place: BOM, scheduledMs: t - 25 * MIN, actualMs: t - 18 * MIN,
            terminal: '2', baggage: '5',
          },
          status: 'landed',
          rawStatus: 'Arrived',
          landedMs: t - 20 * MIN,
        })],
        pending: [],
      };
    },
  },
];
