// What to do about a flight that is not going to operate.
//
// ── IT RENDERS, IT DOES NOT SEARCH ──────────────────────────────────────────
//
// Everything in here was found by the server at the moment the cancellation was
// seen: the board walked, every row judged against the leg the passenger is
// booked onto next, the answer stored beside that flight's state. This opens,
// asks for it, and draws it. No provider call happens on this path at any
// point, which is why it can open at once.
//
// ── WHAT IT IS NOT, AND THE SCREEN SAYS SO ──────────────────────────────────
//
// This app has no fares, no seat availability and no way to book anything. It
// knows which flights EXIST on a route and when they leave, and that is the
// whole of it. A list of flights beside a cancelled one looks exactly like a
// rebooking screen, so the drawer states the difference in words rather than
// leaving somebody to discover it at a desk. See the note at the footer.
//
// ── THE SHELL IS components/DetentSheet.tsx ─────────────────────────────────
//
// An overlay on My Flights rather than a route, for the reason the results
// sheet is one: react-native-screens cannot edge-attach a UIKit form sheet, and
// the trip underneath has to stay mounted and live -- the poller can change the
// very leg this drawer is about while it is open.
//
// UNLIKE THE RESULTS SHEET IT NEEDS NO PROVIDER AND NO CONTEXT. RouteResults is
// mounted under the search Stack and is not reachable here; nothing in this
// file wants it, because the searching already happened somewhere else.
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { DetentSheet, SheetScrollView } from './DetentSheet';
import { sheetDetents } from '../lib/sheet';
import {
  CARD_GAP, CARD_PAD, DIM, GREEN,
} from '../lib/cards';
import { getStatusColor, boardClock } from '../lib/flightstatus';
import { API_BASE } from '../lib/saved';
import {
  fetchAlternatives, connectionRows, searchAgeMinutes,
  type Alternatives, type AlternativeRow,
} from '../lib/alternatives';
import type { SavedFlight } from '../lib/storage';

const MONO = 'JetBrainsMono_400Regular';
const MONO_BOLD = 'JetBrainsMono_700Bold';
const SANS = 'Inter_400Regular';
const SANS_SEMI = 'Inter_600SemiBold';

// THE SMALL DETENT'S OWN HEIGHT, which is the one thing sheetDetents cannot
// know: the grabber's clearance, the headline, the route line under it and the
// air beneath. Enough that the first thing visible is WHAT HAPPENED rather than
// a list of flights with no subject.
const DRAWER_SMALL_HEIGHT = 168;

// ── HOW FAR IT HOLDS OFF THE EDGES WHILE IT IS SHORT ────────────────────────
//
// FIFTEEN POINTS, CLOSING TO NOTHING AT THE TOP DETENT. Short, the drawer is a
// card lifted off the trip behind it; full height, it is the screen and a gap
// down the sides would read as a rendering fault rather than as a lift.
//
// THE CONTENT RIDES INSIDE IT, so this is free of the content's own padding
// and no longer bounded by it. The 16 on the head and the body is measured from
// the surface's edge at every height -- see the note at DetentSheet's slot,
// where holding that steady is what moved the content inside in the first
// place. Fifteen points of lift beside sixteen of padding is the card's own
// margin, not a subtraction from the text's.
const DRAWER_INSET = 15;

// ── THE SURFACE, A STEP ABOVE THE PAGE AND NO FURTHER ───────────────────────
//
// rgb(22,22,24) RATHER THAN THE PAGE'S rgb(10,10,10), so the drawer reads as a
// layer over the trip rather than as more of it. The blue in the last channel
// is UIKit's -- its dark greys are very slightly cool -- and two points of it
// is enough to register beside a neutral page.
//
// AND NOT UIKit's OWN #1C1C1E, WHICH WAS THE FIRST CHOICE. That value is
// rgb(28,28,30), and DIM at the 0.52 this app settled on reads 4.49:1 against
// it -- under the 4.5 floor, four days after every ink in the app was raised to
// clear it. rgb(22,22,24) reads 4.59:1 and keeps it. The lift is slightly
// weaker and the text stays legible, which is the trade that was already made
// once and should not be unmade by a background.
const DRAWER_SURFACE = 'rgb(22,22,24)';

// ── THE AIR AFTER THE LAST ROW, WHICH IS NOT THE SAME AS AIR AT THE BOTTOM ──
//
// FIFTY-SIX POINTS OF CONTENT PADDING, and it only exists once somebody has
// SCROLLED TO THE END. contentContainerStyle padding sits after the last child;
// a list taller than its frame never shows it, and the drawer's list is taller
// than its frame at every detent but the largest. That is why raising this
// number did nothing at the small detent -- see DRAWER_EDGE_PAD, which is the
// one that governs there.
const DRAWER_BOTTOM_PAD = 56;

// ── AND THE GAP BETWEEN THE LIST AND THE SURFACE'S LOWER EDGE ───────────────
//
// THE LIST'S FRAME STOPS HERE, so the clip that ends it lands with air under it
// instead of through a line of text.
//
// THE TAB BAR'S INSET PLUS TWELVE. This sheet is drawn BENEATH the UITabBar --
// a view in a tab's content always is -- so the surface runs on behind the bar
// while the content must not, and the clearance has to carry the bar's own
// height as well as the gap that is wanted under the last row.
//
// TWELVE RATHER THAN NOTHING because a list cut exactly at the edge still reads
// as cut. Twelve is enough to show that the row below is a row and not a
// rendering fault, which is what a scrollable list wants to say at a detent
// where it cannot be scrolled.
//
// IT IS FRAME PADDING, NOT CONTENT PADDING, and that distinction is the other
// half of the fix: content padding is after the last child and is unreachable
// while the list overflows; frame padding shortens the scrollable box itself
// and so is honoured at every height.
const DRAWER_EDGE_PAD = 12;

function hhmm(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ── HOW OLD THE ANSWER IS, IN WORDS ─────────────────────────────────────────
//
// THE AGE OF THE SEARCH, NOT OF THE FETCH. A read a second ago over a search
// from this morning is a search from this morning, and the number that matters
// to somebody deciding whether to trust a departure time is the second one.
//
// ROUNDED DOWN TO SOMETHING A PERSON WOULD SAY. "Checked 3 hours ago" is the
// useful precision; "checked 187 minutes ago" is a machine talking.
function ageWords(mins: number | null): string | null {
  if (mins === null) return null;
  if (mins < 2) return 'Checked just now';
  if (mins < 60) return `Checked ${mins} minutes ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `Checked ${h} hour${h === 1 ? '' : 's'} ago`;
  const d = Math.round(h / 24);
  return `Checked ${d} day${d === 1 ? '' : 's'} ago`;
}

// ── ONE FLIGHT ──────────────────────────────────────────────────────────────
//
// THE TIME LEADS, because the only question being asked of this list is when
// somebody could leave. The number and the carrier sit under it in the identity
// grey the rest of the app uses for exactly that pair, on one line, the way the
// open card and the collapsed row both now set them.
//
// THE LAYOVER IS ONLY EVER SHOWN WHERE IT MEANS SOMETHING -- on a row in the
// connection list, where the whole point is how much room is left at the hub.
// In the destination list it would be an answer to a question nobody asked.
// `from` IS THE AIRPORT EVERY ROW LEAVES FROM -- the disrupted leg's own
// origin -- and it names the clock's zone. The server's `tz` is empty on these
// rows, because a board's departure strings carry none, and its `time` is the
// 12-hour form; the row reads the ISO instead, like every other clock.
function Row({ r, showLayover, from }: { r: AlternativeRow; showLayover: boolean; from: string | null }) {
  const tight = r.connects === 'at_risk';
  const z = boardClock(r.departureIso, r.time, from);
  return (
    <View style={s.row}>
      <View style={s.rowMain}>
        <Text style={s.rowTime} numberOfLines={1}>
          {z.clock}
          {z.zone !== null && <Text style={s.rowZone}>{` ${z.zone}`}</Text>}
          {z.yours !== null && <Text style={s.rowYours}>{`  ${z.yours}`}</Text>}
        </Text>
        <Text style={s.rowIdent} numberOfLines={1}>
          {r.flightNumber}
          {r.airline !== null && (
            <>
              {'  ·  '}
              <Text style={s.rowIdentName}>{r.airline}</Text>
            </>
          )}
        </Text>
      </View>
      <View style={s.rowSide}>
        <Text style={s.rowDay} numberOfLines={1}>{r.day}</Text>
        {showLayover && r.layoverMinutes !== null && (
          // TIGHT IS AMBER AND NOTHING ELSE IS COLOURED. The app's one word for
          // "this is at risk" is already amber on the connection warning and on
          // a delayed leg; a comfortable layover is ordinary and takes the
          // ordinary ink.
          <Text style={[s.rowLayover, tight && s.rowLayoverTight]} numberOfLines={1}>
            {`${hhmm(r.layoverMinutes)} to connect`}
          </Text>
        )}
        {/* ── AND THE ROW THAT CANNOT BE TESTED SAYS SO ──────────────────
            The board gave a destination and no arrival time. That row is a
            real flight to the right place, so it is here; what it cannot do
            is promise a connection, and an unmarked row in this list would
            do exactly that by sitting among ones that can. */}
        {!showLayover && r.connects === 'unknown' && (
          <Text style={s.rowUnknown} numberOfLines={1}>{'arrival time not published'}</Text>
        )}
      </View>
    </View>
  );
}

function Section({ head, note, rows, showLayover, from }: {
  head: string; note?: string | null; rows: AlternativeRow[]; showLayover: boolean; from: string | null;
}) {
  if (rows.length === 0) return null;
  return (
    <View style={s.section}>
      <Text style={s.sectionHead}>{head.toUpperCase()}</Text>
      {note !== null && note !== undefined && <Text style={s.sectionNote}>{note}</Text>}
      {/* ── NO CARD UNDER THESE ROWS, AND THE SHEET IS WHY ──────────────────
          THEY SAT ON SURFACE_1, which is this app's card: 4.5% white over
          whatever is behind it. That reads correctly on the page, where it
          lifts a group off rgb(10,10,10). On the drawer's own surface it
          stacked one lift on another -- rgb(22,22,24) became rgb(32,32,34) --
          and DIM at 0.52 against that is 4.39:1, under the floor every ink in
          the app was raised to clear.
          THE SHEET IS ALREADY THE RAISED LAYER. A card inside it is a second
          answer to a question the surface has answered, so the rows sit
          directly on it and the hairline rules do the grouping. Nothing is
          lost but a fill, and 0.2 of contrast comes back. */}
      {rows.map((r, i) => (
        <View key={`${r.flightNumber}-${r.date}-${i}`}>
          {i > 0 && <View style={s.rowRule} />}
          <Row r={r} showLayover={showLayover} from={from} />
        </View>
      ))}
    </View>
  );
}

export function AlternativesDrawer({ leg, onClose }: {
  // THE LEG THE DRAWER IS ABOUT. null is closed; the owner unmounts on
  // onDismissed rather than on the tap, so the spring has somewhere to land.
  leg: SavedFlight | null;
  onClose: () => void;
}) {
  const insets = useSafeAreaInsets();
  const { height: winHeight } = useWindowDimensions();
  const heights = sheetDetents(winHeight, insets.bottom, DRAWER_SMALL_HEIGHT);

  const [detent, setDetent] = useState(1);
  const [closing, setClosing] = useState(false);
  const [data, setData] = useState<Alternatives | null>(null);
  // THREE STATES AND NOT TWO. "asking" is not "nothing found": the first is a
  // spinner's worth of patience, the second is an answer. Collapsing them shows
  // an empty list for a second on every open.
  const [asking, setAsking] = useState(true);
  const [now, setNow] = useState(() => Date.now());

  // ── THE FIRST READ, AND THE ONE THING AN EFFECT MAY NOT DO ────────────────
  //
  // NOTHING IS SET SYNCHRONOUSLY HERE, and `asking` starts true for exactly
  // that reason. Setting it at the top of the effect would be a state write
  // during the commit that scheduled the effect -- a cascading render, and the
  // lint rule that catches it is right: the drawer already opens in the state
  // this would be putting it into.
  //
  // AND THE RESULT IS DROPPED IF THE DRAWER HAS GONE. A fetch resolves after a
  // dismissal often enough to matter -- the sheet's spring is 0.45s and a cold
  // Cloud Run instance is slower than that -- and writing state into an
  // unmounted drawer is a warning at best and a stale render at worst.
  useEffect(() => {
    if (leg === null) return;
    let alive = true;
    void (async () => {
      const got = await fetchAlternatives(API_BASE, leg);
      if (!alive) return;
      setData(got);
      setNow(Date.now());
      setAsking(false);
    })();
    return () => { alive = false; };
  }, [leg]);

  // THE SAME READ FROM A TAP, where setting `asking` first IS allowed and is
  // the point: the button has to say it is doing something. An event handler is
  // not a render, which is the whole of the difference from the effect above.
  const refresh = useCallback(async (f: SavedFlight) => {
    setAsking(true);
    const got = await fetchAlternatives(API_BASE, f);
    setData(got);
    setNow(Date.now());
    setAsking(false);
  }, []);

  if (leg === null) return null;

  const rows = data?.rows ?? [];
  const connects = connectionRows(data);
  const age = ageWords(searchAgeMinutes(data, now));
  const off = leg.status === 'diverted' ? 'DIVERTED' : 'CANCELLED';
  const dest = data?.destination ?? leg.to.iata;
  // STILL WALKING IS NOT THE SAME AS NOTHING. `done` false means the poller has
  // days left to look at, and saying "nothing on this route" then would be the
  // app reporting an absence it has not established.
  const searching = asking || data === null || data.done === false;

  return (
    <DetentSheet
      detents={heights}
      detent={detent}
      onDetentChange={setDetent}
      closing={closing}
      onDismissRequest={() => setClosing(true)}
      onDismissed={onClose}
      inset={DRAWER_INSET}
      surface={<View style={s.surface} />}
    >
      <View style={s.head}>
        {/* WHAT HAPPENED, FIRST AND IN THE STATUS COLOUR. The small detent shows
            this and the route under it and nothing else, so the drawer opens on
            its subject rather than on a list whose subject is off screen. */}
        <Text style={[s.word, { color: getStatusColor(leg.status) }]} numberOfLines={1}>
          {off}
        </Text>
        <Text style={s.route} numberOfLines={1}>
          {`${leg.from.iata} → ${leg.to.iata}  ·  ${leg.flightNumber}`}
        </Text>
        {age !== null && (
          <View style={s.ageRow}>
            <Text style={s.age} numberOfLines={1}>{age}</Text>
            {/* ── REFRESH RE-READS; IT DOES NOT RE-SEARCH ──────────────────
                The endpoint behind this touches no provider, so this costs
                nothing and is worth offering: the poller rewrites the stored
                answer every couple of minutes, so a read a minute later can
                genuinely be newer. What it cannot do is make the SERVER look
                again -- that would be a second endpoint that spends units, and
                it is not this one. */}
            <TouchableOpacity
              onPress={() => { void refresh(leg); }}
              accessibilityRole="button"
              accessibilityLabel="check again"
              hitSlop={10}
            >
              <Text style={s.refresh}>{asking ? 'CHECKING' : 'CHECK AGAIN'}</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* ── THE LIST, IN A FRAME THAT STOPS SHORT OF THE BAR ────────────
          THE SCROLLABLE BOX IS WHAT CARRIES THE BOTTOM CLEARANCE. The list
          overflows its frame at every detent but the largest, so a clip is how
          it ends rather than an exception -- and a clip through the middle of
          a row is what "no padding at the small detent" was. Shortening the
          frame moves the clip up into air. See DRAWER_EDGE_PAD.
          AND THE CONTENT'S OWN PADDING STAYS, for the other case: once the
          list IS scrollable and somebody reaches the end, DRAWER_BOTTOM_PAD is
          the air under the last paragraph. The two numbers answer different
          questions and neither substitutes for the other. */}
      <View style={[s.listFrame, { paddingBottom: insets.bottom + DRAWER_EDGE_PAD }]}>
      <SheetScrollView
        style={s.listScroll}
        contentContainerStyle={[s.body, { paddingBottom: DRAWER_BOTTOM_PAD }]}
      >
        {/* ── WHAT THE CONNECTION IS FOR, NAMED ──────────────────────────
            A list headed "still makes your connection" is meaningless without
            saying which connection. The server sends a summary of the leg for
            exactly this line. */}
        <Section
          head="Still makes your next flight"
          note={data?.nextLeg?.flightNumber != null
            ? `Onto ${data.nextLeg.flightNumber} from ${data.nextLeg.departureIata ?? dest}`
            : null}
          rows={connects}
          showLayover
          from={data?.origin ?? leg.from.iata}
        />
        <Section
          head={dest !== null ? `Other flights to ${dest}` : 'Other flights'}
          note={connects.length > 0
            ? 'Including ones that would not leave enough time to connect.'
            : null}
          rows={rows}
          showLayover={false}
          from={data?.origin ?? leg.from.iata}
        />

        {rows.length === 0 && (
          <View style={s.empty}>
            <Text style={s.emptyHead}>
              {searching ? 'Still looking' : 'Nothing else on this route'}
            </Text>
            <Text style={s.emptyNote}>
              {searching
                ? 'Terminal is working through the departure board. This updates on its own.'
                : `No other flight is scheduled on this route in the next ${data?.maxDays ?? 7} days.`}
            </Text>
          </View>
        )}

        {/* ── WHAT THIS LIST IS, SAID PLAINLY ────────────────────────────
            NOT A REBOOKING SCREEN, and it looks exactly like one. Terminal has
            no fares from any provider, no seat availability from any provider,
            and no way to book. It knows which flights exist and when they
            leave. Somebody who reads this list as "these seats are available"
            finds out at a desk, and by then we told them it was fine.
            AND IT IS THE LAST THING, not a disclaimer at the top. It qualifies
            the list, so it sits under it. */}
        <Text style={s.disclaimer}>
          {'These are the flights that exist on this route. Terminal has no seat '
            + 'availability, no fares and no way to book — check with whoever '
            + 'holds your booking before you count on one.'}
        </Text>
      </SheetScrollView>
      </View>
    </DetentSheet>
  );
}

const s = StyleSheet.create({
  // A FLAT FILL, NOT GLASS. The results sheet is chrome over a live map and
  // wants to read as a material; this is a page somebody reads, over a list
  // that is not moving.
  //
  // NO RADIUS AND NO INSET OF ITS OWN. Both are the shell's now: the surface
  // slot carries the animated corners and the animated edges, and this fills
  // it. See DetentSheet's `inset`.
  surface: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: DRAWER_SURFACE,
  },
  head: { paddingTop: 26, paddingHorizontal: 16, paddingBottom: 12 },
  word: { fontFamily: MONO_BOLD, fontSize: 24, letterSpacing: 1 },
  route: { fontFamily: MONO, fontSize: 13, color: DIM, marginTop: 6 },
  ageRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 },
  age: { fontFamily: SANS, fontSize: 11, color: DIM },
  refresh: { fontFamily: SANS_SEMI, fontSize: 11, color: GREEN, letterSpacing: 0.4 },

  // THE SCROLLABLE BOX AND ITS FRAME. flex on both: the slot above is
  // absolutely positioned with all four edges set, so it has a definite height
  // to divide, and the frame takes whatever the head leaves.
  listFrame: { flex: 1 },
  listScroll: { flex: 1 },
  body: { paddingHorizontal: 16 },
  section: { marginBottom: 18 },
  sectionHead: { fontFamily: SANS_SEMI, fontSize: 11, color: DIM, letterSpacing: 0.5, marginBottom: 4 },
  sectionNote: { fontFamily: SANS, fontSize: 11, color: DIM, marginBottom: 8 },

  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: CARD_PAD },
  // THE ONLY THING GROUPING THE ROWS NOW. A hairline at 6% white, which over
  // the drawer's rgb(22,22,24) reads as rgb(36,36,38) -- present without being
  // a border. It is what the card's edge used to do and is cheaper in
  // contrast: a line between two rows costs nothing that sits under text.
  rowRule: { height: 1, backgroundColor: 'rgba(255,255,255,0.06)' },
  rowMain: { flex: 1, gap: 3 },
  rowTime: { fontFamily: MONO_BOLD, fontSize: 17, color: '#ffffff' },
  // The zone a size down in the ident's grey, the phone's time smaller still.
  rowZone: { fontFamily: MONO, fontSize: 12, color: DIM },
  rowYours: { fontFamily: MONO, fontSize: 11, color: DIM },
  rowIdent: { fontFamily: MONO, fontSize: 13, color: DIM },
  rowIdentName: { fontFamily: SANS },
  rowSide: { alignItems: 'flex-end', gap: 3, marginLeft: CARD_GAP },
  rowDay: { fontFamily: MONO, fontSize: 13, color: DIM },
  rowLayover: { fontFamily: MONO, fontSize: 11, color: DIM },
  rowLayoverTight: { color: '#fbbf24' },
  rowUnknown: { fontFamily: SANS, fontSize: 11, color: DIM, maxWidth: 150, textAlign: 'right' },

  empty: { paddingVertical: 8, marginBottom: 18 },
  emptyHead: { fontFamily: MONO_BOLD, fontSize: 15, color: '#ffffff', marginBottom: 6 },
  emptyNote: { fontFamily: SANS, fontSize: 12, color: DIM, lineHeight: 18 },

  disclaimer: { fontFamily: SANS, fontSize: 11, color: DIM, lineHeight: 17, marginTop: 4 },
});
