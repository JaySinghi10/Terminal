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
import { offsetMinutesAt, zoneAbbrAt } from './time';
import type { AlternativeRow, Alternatives } from './alternatives';

// ── HOW A FIXTURE IS RECOGNISED ─────────────────────────────────────────────
//
// THE FLIGHT NUMBER, because it is the one field that is on both a SavedFlight
// and a PendingLeg, is part of both ids, and survives every copy the store
// makes. ZZ is not an assigned IATA carrier code, so nothing real can collide
// with it; the number is also what a person sees on screen, which makes a
// fixture obvious rather than something to be caught out by.
export const DEV_PREFIX = 'ZZ9';

// ── AND BY ITS TRIP, FOR THE SCREENSHOT FLIGHTS ─────────────────────────────
//
// THE WEBSITE'S SCREENSHOTS NEED REAL-LOOKING FLIGHTS -- BA177, not ZZ907 --
// and those cannot be told apart by number. Every fixture is installed inside a
// trip whose id starts "dev-" (see tripId below), where a real trip's id starts
// "trip:" (newTripId in lib/saved), so the trip is the second mark. The number
// stays the first: a pending leg need not belong to a trip at all.
export const DEV_TRIP_PREFIX = 'dev-';

export function isDevFixture(
  f: { flightNumber?: string | null; tripId?: string | null } | null | undefined,
): boolean {
  if ((f?.flightNumber ?? '').toUpperCase().startsWith(DEV_PREFIX)) return true;
  return typeof f?.tripId === 'string' && f.tripId.startsWith(DEV_TRIP_PREFIX);
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
  // WHETHER THE PROVIDER HAS LIVE COVERAGE. True unless a scenario says not,
  // which is the ordinary case at the airports these fixtures use; a gate time
  // on a movement without it is not believed. See gateTs in lib/departure.ts.
  live?: boolean;
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
    liveFeed: a.live ?? true,
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
  // WHERE A DIVERTED LEG ACTUALLY LANDED, as the server delivers it: a IATA
  // code, already translated from FR24's ICAO. Only the diverted scenario sets
  // it; every other fixture leaves it null, which is what an ordinary flight
  // carries and what the card must render as a question mark.
  divertedTo?: string | null;
  // WHO FLIES IT, ON WHAT, UNDER WHICH REFERENCE: the test values unless a
  // scenario says otherwise, and the website's screenshot flights say otherwise.
  airline?: string;
  aircraft?: string;
  registration?: string;
  pnr?: string;
  // WHEN FR24 SAW IT TAKE OFF, written as the server delivers it. Only the
  // departure scenarios set it.
  takeoffMs?: number | null;
  // WHEN THE PROVIDER LAST SPOKE, if not this moment: the stale departure
  // scenario is a record the count may no longer trust.
  updatedAt?: number;
};

function leg(a: LegArgs): SavedFlight {
  const now = Date.now();
  const date = dayOf(a.from.scheduledMs, a.from.place.offset);
  return {
    id: makeFlightId(a.number, date),
    flightNumber: a.number,
    airline: a.airline ?? 'Terminal Test Air',
    flightDate: date,
    status: a.status ?? 'scheduled',
    from: endpoint(a.from),
    to: endpoint(a.to),
    aircraftModel: a.aircraft ?? 'Airbus A320',
    aircraftRegistration: a.registration ?? 'VT-ZZZ',
    savedAt: now,
    updatedAt: a.updatedAt ?? now,
    landedAt: a.landedMs ?? null,
    // THE AUTHORITATIVE LANDING, and it is the only thing that makes
    // effectiveStatus say 'landed' -- see its note on the one promotion. A
    // fixture that set status alone would be demoted back to 'active' and the
    // landed rendering would never appear.
    landedUtc: a.landedMs != null ? new Date(a.landedMs).toISOString().slice(0, 16) + 'Z' : null,
    landingSource: a.landedMs != null ? 'fr24' : null,
    landingCheck: a.landedMs != null ? 'landed' : null,
    landingCheckedAt: a.landedMs != null ? now : null,
    divertedTo: a.divertedTo ?? null,
    // FR24's OWN FORMAT: UTC with no zone marker, to the second. landedUtcToTs
    // is what reads it, so a fixture written any other way would test a path
    // the wire never takes.
    takeoffUtc: a.takeoffMs != null ? new Date(a.takeoffMs).toISOString().slice(0, 19) : null,
    archivedAt: null,
    remindersSetAt: null,
    tripId: a.tripId ?? null,
    pnr: a.pnr ?? 'ZZFIX1',
    operatingFlightNumber: null,
    operatedBy: null,
    rawStatus: a.rawStatus ?? 'Expected',
    // THE CURRENT VERSION, so normalizeRecord leaves these alone rather than
    // running a migration over them on the first read.
    schemaVersion: 15,
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
function tripLegs(tripId: string, opts: {
  leg2ArrivesAt?: number | null; leg1Status?: string; leg2Status?: string;
  // WHICH TERMINAL THE LAST LEG LEAVES FROM, so one scenario can show a
  // connection that changes buildings and another can show one that does not.
  // Leg 2 lands at BLR terminal 1; leaving this alone is the same-terminal
  // case, and anything else is the change. See the two connection scenarios.
  leg3Terminal?: string;
} = {}): SavedFlight[] {
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
      from: {
        place: DEL, scheduledMs: l2Dep, terminal: '3', gate: 'B12',
        // ── A LATE ARRIVAL CAME FROM A LATE DEPARTURE ─────────────────────
        //
        // THE DELAY WAS ONLY EVER ON THE ARRIVAL, which is what the connection
        // arithmetic reads and is why it was put there -- and it left the leg
        // with a delayed arrival, an on-time departure, and no departure delay
        // at all. That is not a shape a real record takes, and it is the one
        // field the collapsed row's DELAYED chip reads: displayStatus asks for
        // the DEPARTURE delay, so a fixture with none could never show the
        // chip however late it landed.
        //
        // SO THE DEPARTURE SLIPS BY THE SAME AMOUNT. The aircraft leaves late
        // and lands late by the same margin, which is the ordinary case and
        // makes the whole leg consistent: the chip, the countdown and the
        // connection warning are now all reading one delay.
        estimatedMs: opts.leg2ArrivesAt == null ? null : l2Dep + (opts.leg2ArrivesAt - l2Arr),
      },
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
      // THE FIXTURE'S WHOLE POINT, NOW THAT THERE IS SOMETHING TO SHOW. This
      // leg is DEL -> BLR; HYD is a real diversion for it and is far enough
      // from the scheduled arrival to be obviously not it. Before this the
      // scenario could only prove the card refused to name a destination.
      divertedTo: opts.leg2Status === 'diverted' ? 'HYD' : null,
    }),
    leg({
      number: 'ZZ903', tripId,
      from: { place: BLR, scheduledMs: l3Dep, terminal: opts.leg3Terminal ?? '1', gate: 'C3' },
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
const tripId = () => `${DEV_TRIP_PREFIX}${Date.now()}`;

function doubtLeg(trip: string | null): PendingLeg {
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
    // SEE THE SCENARIO: a pending leg reaches the trip screen -- and so becomes
    // openable -- only by sharing a journey with a saved one.
    tripId: trip,
    legStatus: 'scheduled',
    // THE WHOLE POINT OF THIS ONE: the airline cancelled the booking and named
    // no flight, so the leg is in doubt rather than cancelled. See
    // bookingCancelled in pendingRules.
    bookingCancelled: true,
    arrivalTime: '20:55',
    arrivalDate: null,
  };
}

// ── ONE DEPARTURE, AT DIFFERENT MOMENTS AFTER ITS TIME ─────────────────────
//
// BOM -> DEL, ONE LEG, OWNED, so the trip screen opens it as the current card
// and the rows and the Deck all have it. Each scenario is the same flight at a
// different point between its scheduled time and its takeoff: counting at the
// gate, counting from an announced delay, off the gate, off the ground, and a
// record too old to count on.
//
// WHOLE MINUTES, as the provider's times are, so the figures read exactly: the
// schedule is set a whole number of minutes before the current minute.
//
// THE COUNT STOPS THIRTY MINUTES AFTER INSTALL. A fixture's updatedAt is the
// moment it was installed and nothing refreshes a fixture, so the counting
// scenarios go quiet when COUNT_FRESH_MS says a real record would. Install one
// again to see it count.
function departureLeg(o: {
  number: string;
  schedAgo: number;       // minutes since the scheduled departure
  estimateLate?: number;  // the airline's announced delay, in minutes
  gateLate?: number;      // minutes after the schedule it left the gate
  takeoffAgo?: number;    // minutes since FR24 saw it take off
  updatedAgo?: number;    // minutes since the provider last spoke
  status: string;
  rawStatus: string;
}): SavedFlight {
  const t = Date.now();
  const sched = Math.floor(t / MIN) * MIN - o.schedAgo * MIN;
  const block = 2 * HOUR + 10 * MIN;
  const late = (o.gateLate ?? o.estimateLate ?? 0) * MIN;
  return leg({
    number: o.number, tripId: tripId(),
    from: {
      place: BOM, scheduledMs: sched, terminal: '2', gate: 'A7',
      estimatedMs: o.estimateLate != null ? sched + o.estimateLate * MIN : null,
      actualMs: o.gateLate != null ? sched + o.gateLate * MIN : null,
    },
    to: {
      place: DEL, scheduledMs: sched + block, terminal: '3',
      estimatedMs: late ? sched + block + late : null,
    },
    status: o.status,
    rawStatus: o.rawStatus,
    takeoffMs: o.takeoffAgo != null ? Math.floor(t / MIN) * MIN - o.takeoffAgo * MIN : null,
    updatedAt: o.updatedAgo != null ? t - o.updatedAgo * MIN : undefined,
  });
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
    note: 'Just over the two-hour international minimum, and no terminal change.',
    // ── NEAR THE FLOOR, NOT MID-BAND ──────────────────────────────────────
    //
    // IT LEFT 135 MINUTES, which is correctly at risk -- the amber band is the
    // thirty minutes ABOVE the minimum -- and read as nonsense on screen next
    // to the figure: "2h 15m left" does not look tight against a two-hour
    // rule. Nothing was wrong with the arithmetic or with this number; it was
    // simply the least convincing example the band can produce.
    //
    // 125 MINUTES SITS FIVE ABOVE THE FLOOR, so the demonstration matches what
    // the word means. The band is unchanged and a real 135-minute connection
    // still warns, which is the behaviour and is worth seeing deliberately
    // rather than by accident.
    build: () => ({ flights: tripLegs(tripId(), { leg2ArrivesAt: Date.now() + (14 * 60 - 125) * MIN }), pending: [] }),
  },
  {
    key: 'trip-miss',
    label: 'Trip · connection missed',
    note: 'An hour left, under the international minimum, and a terminal change on top.',
    // THE TERMINAL CHANGE RIDES ON THIS ONE so both halves of the terminal
    // rule are reachable from the menu: the at-risk scenario above keeps leg 3
    // at BLR terminal 1 and reads "same terminal", and this one moves it to 2
    // and reads "T1 to T2". The two scenarios differ in more than the delay
    // for that reason, which is the point of a fixture menu rather than a
    // defect in it.
    build: () => ({
      flights: tripLegs(tripId(), { leg2ArrivesAt: Date.now() + 13 * HOUR, leg3Terminal: '2' }),
      pending: [],
    }),
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
    note: 'The middle leg is diverted, and the card names where it actually went.',
    build: () => ({ flights: tripLegs(tripId(), { leg2Status: 'diverted' }), pending: [] }),
  },
  {
    key: 'booking-doubt',
    label: 'Booking cancelled, legs unknown',
    note: 'An unpublished leg in a trip whose booking the airline cancelled without naming a flight.',
    // ── IT NEEDS A TRIP TO BE OPENABLE ───────────────────────────────────
    //
    // A PENDING LEG WITH NO TRIP RENDERS ON HOME, where the row is a summary
    // line and cannot be expanded at all -- which is what made this fixture
    // untappable. unpublishedOf matches pending legs to a journey by tripId,
    // so the doubt only reaches the trip screen's UnpublishedLeg -- the card
    // with the reference, the sentence and the open/close toggle -- when it
    // shares one with a saved leg.
    //
    // SO IT SHIPS WITH A FLOWN-FROM LEG BESIDE IT, which is also the honest
    // shape: a booking whose reference the airline cancelled is a booking, and
    // a booking has more than one flight in it more often than not.
    build: () => {
      const id = tripId();
      const t = Date.now();
      return {
        flights: [leg({
          number: 'ZZ905', tripId: id,
          from: { place: BOM, scheduledMs: t + 26 * HOUR, terminal: '2', gate: 'A4' },
          to: { place: DEL, scheduledMs: t + 28 * HOUR, terminal: '3' },
        })],
        pending: [doubtLeg(id)],
      };
    },
  },
  {
    key: 'in-air',
    label: 'In the air',
    note: 'Departed an hour ago, an hour to run. Draws the progress bar and the arc.',
    // OWNED, NOT WATCHED. tripId null is a flight somebody is following rather
    // than flying, and Home draws those with the watchlist card -- so this
    // fixture exercised the wrong surface entirely. A trip of one leg is still
    // a trip; see the tripId note on SavedFlight.
    build: () => {
      const t = Date.now();
      return {
        flights: [leg({
          number: 'ZZ907', tripId: tripId(),
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
    note: 'Two legs, both down. The second landed twenty minutes ago with a belt.',
    // ── TWO LEGS, AND THE BELT IS ON THE SECOND ──────────────────────────
    //
    // OWNED, for the reason the in-air one is. And TWO legs rather than one,
    // because a belt on a COLLAPSED row can only ever appear on the last leg
    // of a journey: bagEligible refuses an intermediate one, since a
    // through-checked bag is not on any belt at a connection. A one-leg
    // fixture could only ever show the belt on the open card.
    //
    // SO BOTH PATHS ARE REACHABLE HERE. The trip opens on the second leg and
    // its belt is on the card; tap the first leg and the second collapses,
    // and the belt is on the row. Tapping is the only way to see the second,
    // which is the behaviour rather than a shortcoming of the fixture.
    build: () => {
      const t = Date.now();
      const id = tripId();
      return {
        flights: [
          leg({
            number: 'ZZ909', tripId: id,
            from: { place: BOM, scheduledMs: t - 6 * HOUR, actualMs: t - 6 * HOUR, terminal: '2' },
            to: { place: DEL, scheduledMs: t - 4 * HOUR, actualMs: t - 4 * HOUR, terminal: '3' },
            status: 'landed',
            rawStatus: 'Arrived',
            landedMs: t - 4 * HOUR,
          }),
          leg({
            number: 'ZZ908', tripId: id,
            from: { place: DEL, scheduledMs: t - 3 * HOUR, actualMs: t - 3 * HOUR, terminal: '3' },
            to: {
              place: BLR, scheduledMs: t - 25 * MIN, actualMs: t - 18 * MIN,
              terminal: '1', baggage: '5',
            },
            status: 'landed',
            rawStatus: 'Arrived',
            landedMs: t - 20 * MIN,
          }),
        ],
        pending: [],
      };
    },
  },
  {
    key: 'dep-counting',
    label: 'Departure · 12 min past, still at the gate',
    note: 'Nothing reported since its time. The pill reads DELAYED 12M, and 13M a minute later.',
    build: () => ({
      flights: [departureLeg({ number: 'ZZ911', schedAgo: 12, status: 'scheduled', rawStatus: 'Boarding' })],
      pending: [],
    }),
  },
  {
    key: 'dep-counting-estimate',
    label: 'Departure · announced 45 min late',
    note: 'Ten minutes past its time and announced forty-five late: the count starts at 45M, not 10M.',
    build: () => ({
      flights: [departureLeg({
        number: 'ZZ912', schedAgo: 10, estimateLate: 45, status: 'scheduled', rawStatus: 'Delayed',
      })],
      pending: [],
    }),
  },
  {
    key: 'dep-left-gate',
    label: 'Departure · left the gate 18 min late',
    note: 'Off the gate seven minutes ago. The count has stopped at 18m and the card says left the gate.',
    build: () => ({
      flights: [departureLeg({
        number: 'ZZ913', schedAgo: 25, gateLate: 18, status: 'active', rawStatus: 'Departed',
      })],
      pending: [],
    }),
  },
  {
    key: 'dep-took-off',
    label: 'Departure · FR24 saw it take off',
    note: 'The provider still says Gate Closed; FR24 saw it climb four minutes ago. The card says took off.',
    build: () => ({
      flights: [departureLeg({
        number: 'ZZ914', schedAgo: 30, takeoffAgo: 4, status: 'scheduled', rawStatus: 'GateClosed',
      })],
      pending: [],
    }),
  },
  {
    key: 'dep-stale',
    label: 'Departure · past its time, record 40 min old',
    note: 'Too old to say it has not left: no count, and the card reads as it did before.',
    build: () => ({
      flights: [departureLeg({
        number: 'ZZ915', schedAgo: 50, updatedAgo: 40, status: 'scheduled', rawStatus: 'Boarding',
      })],
      pending: [],
    }),
  },
];

// ══ THE WEBSITE'S SCREENSHOT FLIGHTS ════════════════════════════════════════
//
// terminalaero.com shows the app on an iPhone, and Apple's rule for its device
// frames is the app as it runs -- so the site's pictures are screenshots of
// these, taken on a phone. They are fixtures like every one above: ordinary
// records in the ordinary store, drawn by the ordinary components.
//
// REAL-LOOKING AND NOT REAL. BA177, BA286 and LX325 are real numbers on real
// routes, flown here on made-up times anchored to now. Nothing about them comes
// from the flight data provider, and nothing may: provider data cannot sit on a
// public page. Their trip id keeps them off every network path (isDevFixture),
// and devAlternatives answers the cancellation sheet in place of the server.
//
// NO INDIAN AIRPORTS, by the site's own rule: London, New York, San Francisco
// and Zurich.
//
// EACH SHOT MAY CARRY A NOTICE: the notification that moment brings, in the
// server's own words -- notify.py subject() and render(), which this mirrors;
// change one, change both -- shown by profile.tsx a few seconds after install,
// as a local notification (which iOS draws exactly as it draws a push) or as
// the app's own undo banner.

type SitePlaceDef = { iata: string; airport: string; city: string; short: string; tz: string };

const SITE_PLACES = {
  LHR: { iata: 'LHR', airport: 'London Heathrow', city: 'London', short: 'Heathrow', tz: 'Europe/London' },
  JFK: { iata: 'JFK', airport: 'New York John F Kennedy', city: 'New York', short: 'John F Kennedy', tz: 'America/New_York' },
  SFO: { iata: 'SFO', airport: 'San Francisco International', city: 'San Francisco', short: 'San Francisco', tz: 'America/Los_Angeles' },
  ZRH: { iata: 'ZRH', airport: 'Zurich', city: 'Zurich', short: 'Zurich', tz: 'Europe/Zurich' },
} satisfies Record<string, SitePlaceDef>;

// THE ZONE AT THAT MOMENT, not a constant: the shots may be taken either side
// of a clock change, and the label and the offset must agree with the clocks.
// The same two helpers the app's own clocks use, so "BST" here is "BST" there.
function sitePlace(code: keyof typeof SITE_PLACES, at: number): Place {
  const d: SitePlaceDef = SITE_PLACES[code];
  return {
    iata: d.iata, airport: d.airport, city: d.city, short: d.short, tz: d.tz,
    tzLabel: zoneAbbrAt(at, d.tz) ?? '',
    offset: offsetMinutesAt(at, d.tz) ?? 0,
  };
}

// "5:05 PM", the server's _clock: a 12-hour clock with no zone.
function clock12(ms: number, offsetMin: number): string {
  return clockText(ms, offsetMin, '').trim();
}

// notify.py _at: every clock a push prints is 24-hour with its zone, "21:15
// BST", as the app prints them.
function clockText24(ms: number, offsetMin: number, tzLabel: string): string {
  const d = new Date(ms + offsetMin * 60_000);
  const hm = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
  return tzLabel ? `${hm} ${tzLabel}` : hm;
}

// notify.py _24h, for a clock that arrives as text: "17:05" from "5:05 PM".
function hm24(text: string): string {
  return text.replace(/\b(\d{1,2}):(\d{2})\s?([AP])M\b/gi, (_m, h: string, mm: string, ap: string) =>
    `${String((Number(h) % 12) + (ap.toUpperCase() === 'P' ? 12 : 0)).padStart(2, '0')}:${mm}`);
}

// notify.py subject and TITLE_MAX: the route and the number, by city when it
// fits on one lock-screen line and by airport code when it would be cut off.
const TITLE_MAX = 26;
function routeTitle(from: { city: string; iata: string }, to: { city: string; iata: string }, number: string): string {
  const byCity = `${from.city} → ${to.city} · ${number}`;
  return byCity.length <= TITLE_MAX ? byCity : `${from.iata} → ${to.iata} · ${number}`;
}

// notify.py _day_label: "today", "tomorrow", a weekday inside the week, or
// "25 Sep" beyond it, all read in the departure airport's own day.
function dayWord(ms: number, now: number, offsetMin: number): string {
  const day = (x: number) => Math.floor((x + offsetMin * MIN) / (24 * HOUR));
  const d = day(ms) - day(now);
  if (d <= 0) return 'today';
  if (d === 1) return 'tomorrow';
  const at = new Date(ms + offsetMin * MIN);
  if (d < 7) {
    return ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][at.getUTCDay()];
  }
  return `${at.getUTCDate()} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][at.getUTCMonth()]}`;
}

// notify.py _early_or_late, over _duration: "38 min early", "1 h 05 min late",
// "on time" at the minute. How the landing summary says how it did.
function earlyOrLate(offsetMin: number): string {
  if (offsetMin === 0) return 'on time';
  const m = Math.abs(offsetMin);
  const h = Math.floor(m / 60);
  const d = m < 60 ? `${m} min` : m % 60 === 0 ? `${h} h` : `${h} h ${String(m % 60).padStart(2, '0')} min`;
  return `${d} ${offsetMin > 0 ? 'late' : 'early'}`;
}

// notify.py _when: "today at 17:05 PDT", "on Sunday at ...".
function whenWords(day: string, time: string, tz: string): string {
  const d = day === 'today' || day === 'tomorrow' ? day : `on ${day}`;
  return `${d} at ${hm24(time)}${tz ? ` ${tz}` : ''}`;
}

export type SiteNotice =
  | { kind: 'push'; title: string; body: string }
  | { kind: 'undo'; text: string };

export type SiteShot = {
  key: string;
  label: string;
  note: string;
  build: () => { flights: SavedFlight[]; pending: PendingLeg[]; notice: SiteNotice | null };
};

const BA177 = { airline: 'British Airways', aircraft: 'Boeing 777-200', registration: 'G-TRML', pnr: 'QX7R2P' };
const BA286 = { airline: 'British Airways', aircraft: 'Airbus A380-800', registration: 'G-TRMA', pnr: 'QX7R2P' };
const LX325 = { airline: 'Swiss', aircraft: 'Airbus A220-300', registration: 'HB-TRM', pnr: 'QX7R2P' };

// LONDON TO NEW YORK IS ABOUT EIGHT HOURS; SAN FRANCISCO TO LONDON ABOUT TEN,
// AND LONDON TO ZURICH NEARLY TWO. The layover is the one the site's copy has:
// two hours forty-five.
const BLOCK_177 = 8 * HOUR + 5 * MIN;
const BLOCK_286 = 10 * HOUR + 15 * MIN;
const BLOCK_325 = HOUR + 45 * MIN;
const LAYOVER = 2 * HOUR + 45 * MIN;

// ── BA177, ONE FLIGHT THROUGH ITS DAY ──────────────────────────────────────
function ba177(stage: 'gate' | 'delay' | 'air' | 'landed' | 'belt') {
  const t = Date.now();
  const lhr = sitePlace('LHR', t);
  const jfk = sitePlace('JFK', t);
  const title = routeTitle(lhr, jfk, 'BA177');
  const base = { ...BA177, number: 'BA177', tripId: tripId() };
  if (stage === 'gate' || stage === 'delay') {
    const dep = t + 80 * MIN;
    const slip = stage === 'delay' ? 25 * MIN : 0;
    const flight = leg({
      ...base,
      from: { place: lhr, scheduledMs: dep, estimatedMs: slip ? dep + slip : null, terminal: '5', gate: 'B32' },
      to: { place: jfk, scheduledMs: dep + BLOCK_177, estimatedMs: slip ? dep + BLOCK_177 + slip : null, terminal: '8' },
      rawStatus: slip ? 'Delayed' : 'Expected',
    });
    const body = slip
      ? `Your flight is delayed 25 min, now leaves at ${clockText24(dep + slip, lhr.offset, lhr.tzLabel)}`
      : "Your flight's gate changed from B24 to B32";
    return { flight, notice: { kind: 'push' as const, title, body } };
  }
  if (stage === 'air') {
    const dep = t - 70 * MIN;
    const due = dep + BLOCK_177 + 5 * MIN;
    const flight = leg({
      ...base,
      from: { place: lhr, scheduledMs: dep, actualMs: dep + 10 * MIN, terminal: '5', gate: 'B32' },
      to: { place: jfk, scheduledMs: dep + BLOCK_177, estimatedMs: due, terminal: '8' },
      status: 'active',
      rawStatus: 'EnRoute',
    });
    return { flight, notice: { kind: 'push' as const, title, body: `Your flight took off and lands around ${clockText24(due, jfk.offset, jfk.tzLabel)}` } };
  }
  const down = stage === 'belt' ? t - 14 * MIN : t - 3 * MIN;
  const sched = down - 9 * MIN;
  const dep = sched - BLOCK_177;
  const flight = leg({
    ...base,
    from: { place: lhr, scheduledMs: dep, actualMs: dep + 12 * MIN, terminal: '5', gate: 'B32' },
    to: { place: jfk, scheduledMs: sched, actualMs: down, terminal: '8', baggage: stage === 'belt' ? '9' : null },
    status: 'landed',
    rawStatus: 'Arrived',
    landedMs: down,
  });
  const body = stage === 'belt'
    ? 'Your bags are on belt 9'
    : `Your flight landed at ${clockText24(down, jfk.offset, jfk.tzLabel)}, ${earlyOrLate(Math.round((down - sched) / MIN))}`;
  return { flight, notice: { kind: 'push' as const, title, body } };
}

// ── BA286 AND LX325, SAN FRANCISCO TO ZURICH THROUGH LONDON ────────────────
function trip286(opts: { lead?: number; late?: number; cancelled?: boolean; landedAgo?: number }): SavedFlight[] {
  const t = Date.now();
  const sfo = sitePlace('SFO', t);
  const lhr = sitePlace('LHR', t);
  const zrh = sitePlace('ZRH', t);
  const id = tripId();
  const landed = opts.landedAgo != null;
  const arr1 = landed ? t - (opts.landedAgo as number) : t + (opts.lead ?? 3 * HOUR + 40 * MIN) + BLOCK_286;
  const dep1 = arr1 - BLOCK_286;
  const dep2 = arr1 + LAYOVER;
  const late = (opts.late ?? 0) * MIN;
  return [
    leg({
      ...BA286, number: 'BA286', tripId: id,
      from: {
        place: sfo, scheduledMs: dep1, terminal: 'I',
        estimatedMs: late ? dep1 + late : null,
        actualMs: landed ? dep1 + 5 * MIN : null,
      },
      to: {
        place: lhr, scheduledMs: arr1, terminal: '5',
        estimatedMs: late ? arr1 + late : null,
        actualMs: landed ? arr1 : null,
      },
      status: opts.cancelled ? 'cancelled' : landed ? 'landed' : 'scheduled',
      rawStatus: opts.cancelled ? 'Canceled' : landed ? 'Arrived' : late ? 'Delayed' : 'Expected',
      landedMs: landed ? arr1 : null,
    }),
    leg({
      ...LX325, number: 'LX325', tripId: id,
      from: { place: lhr, scheduledMs: dep2, terminal: '2' },
      to: { place: zrh, scheduledMs: dep2 + BLOCK_325, terminal: '1' },
    }),
  ];
}

// ── THE CANCELLATION SHEET'S ANSWER, WITHOUT THE SERVER ─────────────────────
//
// WHAT /alternatives WOULD STORE FOR BA286: the other flights from San
// Francisco to London that day, each marked against LX325 by the same rule the
// server uses (_band: under two hours will miss, within half an hour of it is
// at risk). One makes it easily, one only just, one would miss it, and one
// gives no arrival time. Null for every other fixture, whose sheet then says
// it is still looking -- which is what the server said for them anyway.
export function devAlternatives(f: SavedFlight, now: number = Date.now()): Alternatives | null {
  if (f.flightNumber !== 'BA286' || !isDevFixture(f)) return null;
  const dep = Date.parse(f.from.scheduledIso ?? '');
  if (!Number.isFinite(dep)) return null;
  const sfo = sitePlace('SFO', dep);
  const lhr = sitePlace('LHR', dep);
  const nextDep = dep + BLOCK_286 + LAYOVER;
  const others: { number: string; airline: string; at: number; lands: boolean }[] = [
    { number: 'BA284', airline: 'British Airways', at: dep - (2 * HOUR + 35 * MIN), lands: true },
    { number: 'VS20', airline: 'Virgin Atlantic', at: dep + 35 * MIN, lands: true },
    { number: 'UA901', airline: 'United Airlines', at: dep + 70 * MIN, lands: true },
    { number: 'UA930', airline: 'United Airlines', at: dep + 90 * MIN, lands: false },
  ];
  const rows: AlternativeRow[] = others.map(o => {
    const arr = o.lands ? o.at + BLOCK_286 : null;
    const wait = arr === null ? null : Math.round((nextDep - arr) / MIN);
    const connects = wait === null ? 'unknown' : wait < 120 ? 'will_miss' : wait <= 150 ? 'at_risk' : 'comfortable';
    return {
      flightNumber: o.number,
      airline: o.airline,
      destinationIata: 'LHR',
      departureIso: zoned(o.at, sfo.offset),
      arrivalIso: arr === null ? null : zoned(arr, lhr.offset),
      arrivalLabel: arr === null ? null : clockText(arr, lhr.offset, lhr.tzLabel),
      time: clock12(o.at, sfo.offset),
      tz: sfo.tzLabel,
      day: dayWord(o.at, now, sfo.offset),
      date: dayOf(o.at, sfo.offset),
      connects,
      layoverMinutes: wait,
      minimumMinutes: 120,
    };
  });
  return {
    searchedAt: new Date(now - 30_000).toISOString(),
    daysSearched: 1,
    done: true,
    maxDays: 7,
    origin: 'SFO',
    destination: 'LHR',
    nextLeg: {
      flightNumber: 'LX325',
      departureIata: 'LHR',
      arrivalIata: 'ZRH',
      departureIso: zoned(nextDep, lhr.offset),
      departureLabel: clockText(nextDep, lhr.offset, lhr.tzLabel),
    },
    rows,
  };
}

// "San Francisco → London · BA286" is thirty characters: SFO → LHR · BA286.
const BA286_TITLE = routeTitle(SITE_PLACES.SFO, SITE_PLACES.LHR, 'BA286');

export const SITE_SHOTS: SiteShot[] = [
  {
    key: 'site-gate',
    label: 'Site 1 · BA177 gate changed',
    note: 'My Flights. Notification: gate changed from B24 to B32.',
    build: () => { const b = ba177('gate'); return { flights: [b.flight], pending: [], notice: b.notice }; },
  },
  {
    key: 'site-delay',
    label: 'Site 2 · BA177 delayed',
    note: 'My Flights. Notification: Delayed 25 min.',
    build: () => { const b = ba177('delay'); return { flights: [b.flight], pending: [], notice: b.notice }; },
  },
  {
    key: 'site-air',
    label: 'Site 3 · BA177 in the air',
    note: 'My Flights. Notification: Took off.',
    build: () => { const b = ba177('air'); return { flights: [b.flight], pending: [], notice: b.notice }; },
  },
  {
    key: 'site-landed',
    label: 'Site 4 · BA177 landed',
    note: 'My Flights. Notification: Landed.',
    build: () => { const b = ba177('landed'); return { flights: [b.flight], pending: [], notice: b.notice }; },
  },
  {
    key: 'site-belt',
    label: 'Site 5 · BA177 bags on belt 9',
    note: 'My Flights. Notification: Bags on belt 9.',
    build: () => { const b = ba177('belt'); return { flights: [b.flight], pending: [], notice: b.notice }; },
  },
  {
    key: 'site-trip',
    label: 'Site 6 · trip, layover comfortable',
    note: 'My Flights. No notification.',
    build: () => ({ flights: trip286({}), pending: [], notice: null }),
  },
  {
    key: 'site-risk',
    label: 'Site 7 · trip, connection at risk',
    note: 'My Flights. BA286 40 min late. Notification: at risk.',
    build: () => ({
      flights: trip286({ late: 40 }), pending: [],
      notice: { kind: 'push', title: BA286_TITLE, body: 'Your connection to LX325 in London is at risk' },
    }),
  },
  {
    key: 'site-miss',
    label: 'Site 8 · trip, connection won’t hold',
    note: 'My Flights. BA286 70 min late. Notification: won’t hold.',
    build: () => ({
      flights: trip286({ late: 70 }), pending: [],
      notice: { kind: 'push', title: BA286_TITLE, body: "Your connection to LX325 in London won't hold" },
    }),
  },
  {
    key: 'site-cancelled',
    label: 'Site 9 · trip, BA286 cancelled',
    note: 'My Flights, then tap BA286 for the sheet. Notification: Cancelled.',
    build: () => {
      const flights = trip286({ lead: 5 * HOUR + 40 * MIN, cancelled: true });
      const alt = devAlternatives(flights[0]);
      const next = alt?.rows[0];
      const body = next
        ? `Your flight is cancelled, next is ${next.flightNumber} ${whenWords(next.day, next.time, next.tz ?? '')}`
        : 'Your flight is cancelled, finding the next flight';
      return { flights, pending: [], notice: { kind: 'push', title: BA286_TITLE, body } };
    },
  },
  {
    key: 'site-layover',
    label: 'Site 10 · trip, on the layover in London',
    note: 'The Deck tab: where to eat at Heathrow. No notification.',
    build: () => ({ flights: trip286({ landedAgo: 35 * MIN }), pending: [], notice: null }),
  },
  {
    key: 'site-imported',
    label: 'Site 11 · trip, just imported',
    note: 'My Flights. The undo banner: added BA286 +1 more.',
    build: () => ({
      flights: trip286({ lead: 26 * HOUR }), pending: [],
      notice: { kind: 'undo', text: 'added BA286 +1 more' },
    }),
  },
];
