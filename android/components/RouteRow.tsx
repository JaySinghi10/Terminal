// ONE ROW OF THE ROUTE LIST.
//
// IT WAS routeRow, A CLOSURE INSIDE THE SEARCH SCREEN, and every line of the
// markup and every style is unchanged. It became a component because the list
// is about to be drawn in two places -- the search screen's drawer today, a
// native sheet next -- and a closure over one screen's state cannot be drawn by
// the other. Everything it used to read from the screen it reads from
// lib/routeResults now, which both screens are under.
//
// THE ONE THING THAT STAYED OUTSIDE IS THE TAP. What choosing a row DOES --
// select it, and shut the drawer, or whatever the sheet decides -- is the
// caller's business, so it arrives as onPress. The bookmark is not: saving is
// the list's own action wherever the list is drawn.
//
// Flat rows, not cards. Line one carries everything variable-width; line two
// carries the two times and the connector between them, and nothing else may
// join it. The times are sized to their own content and pinned to opposite
// edges of the row, so departures start at the same x and arrivals end at the
// same x while the connector absorbs every point of slack.
// `pinned` only suppresses the in-row "fastest" tag, because the heading
// directly above the pinned row already says the word. Same component, same
// layout, one boolean — there is no second row renderer.
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, ActionSheetIOS } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { airlineFromFlightNumber } from '../lib/airlines';
import { makeFlightId } from '../lib/storage';
import { getStatusColor, stripZoneLabel, formatCountdown, CD_LATE, boardClock } from '../lib/flightstatus';
import { CARD_FILL, CARD_RADIUS, CARD_GAP, CARD_PAD, SURFACE_EDGE } from '../lib/cards';
import {
  useRouteResults, routeDayOf, routeStatusWord, ROUTE_NO_TIME, CATCH_RISKY_NOTE,
  // THE OPTION'S OWN FACTS, from module scope: the row is handed an option and
  // reads its duration and its leg's origin through the accessors, never off a
  // field. See the union in lib/routeResults.
  optDurationMs, legOrigin,
  optFirst, optLast, optLayoverMs, optKey, TRANSFER_LABEL, TRANSFER_NOTE,
  type RouteOption, type RouteItinerary,
} from '../lib/routeResults';

const MONO = 'JetBrainsMono_400Regular';
const MONO_BOLD = 'JetBrainsMono_700Bold';
const SANS = 'Inter_400Regular';

// Ceiling on the DRAWN line only. The connector's box still spans everything
// between the two times; the line is centred inside it, so the gap either side
// is equal by construction at any width.
//
// This replaces a duration-proportional left inset, which was a defect: pushing
// the line right grew the left gap while the right gap stayed fixed, so only the
// single longest flight in a list ever showed equal gaps.
const ROUTE_CONNECTOR_MAX = 120;

type Props = {
  r: RouteOption;
  pinned?: boolean;
  onPress: (r: RouteOption) => void;
};

export function RouteRow({ r, pinned = false, onPress }: Props) {
  const {
    savedFlights, routeResult, routeRowKey, routeLastKey,
    routeFastestKeys, routeSavingKey, saveFromRoute, routeCatchOf,
  } = useRouteResults();
  // A CONNECTION IS ITS OWN ROW, below. A component of its own rather than a
  // branch here, so neither row's hooks depend on which kind of option it is.
  if (r.kind === 'via') return <ViaRow r={r} pinned={pinned} onPress={onPress} />;
  // THE ROW THIS OPTION WRAPS. Everything below reads the leg, exactly as it
  // read the row before the union existed; the key and the fastest marker are
  // the option's, which on a direct option is the same value.
  const leg = r.leg;
  const ms = optDurationMs(r);
  const origin = legOrigin(leg, routeResult?.origin ?? '');
  const destination = leg.destination_iata ?? routeResult?.destination ?? '';
  // EACH END'S CLOCK, NAMED FROM THE DATASET. The board sends no zone, so the
  // airport's own IANA zone supplies it -- see boardClock.
  const depZ = boardClock(leg.departure_scheduled_iso, leg.departure_scheduled, origin || null);
  const arrZ = boardClock(
    leg.arrival_scheduled_iso,
    leg.arrival_scheduled === null ? ROUTE_NO_TIME : stripZoneLabel(leg.arrival_scheduled),
    destination || null,
  );
  // The APPLIED date, never routeDate: that can hold a selection the list has
  // not been re-fetched for, which would open a card for a day the row on
  // screen is not from. Null for an undated board, which is today.
  const rowDate = routeResult?.date ?? null;
  const airline = airlineFromFlightNumber(leg.flight_number);
  // Number AND date, so a row shows saved only when THAT instance is saved.
  //
  // The local calendar date a board row DEPARTS on, read from its own ISO.
  // Not the board's date. An undated board is a rolling twelve hours from now,
  // so its late rows belong to tomorrow — and a record saved from one of those
  // is keyed on the date the backend reports, which is the row's own. Matching
  // the indicator on the board's date instead would leave those rows showing
  // unsaved forever.
  const rowDay = routeDayOf(leg);
  const saved = savedFlights.some(f => f.id === makeFlightId(leg.flight_number, rowDay));
  const pending = routeSavingKey === leg.flight_number;
  const busy = routeSavingKey !== null;
  // Null on the ordinary row, which is most of them. See routeStatusWord.
  const statusWord = routeStatusWord(leg);
  // WHETHER IT CAN STILL BE CAUGHT, at the provider's clock. Only the risky
  // band marks the row itself: a catchable row needs no reassurance, and an
  // uncatchable one is already under the heading that says so. See optCatch.
  const risky = routeCatchOf(r) === 'risky';
  return (
    <TouchableOpacity
      style={[s.routeFlatRow, routeRowKey(r) === routeLastKey && s.routeFlatRowLast]}
      activeOpacity={0.7}
      // Same reasoning as handleSearch and renderSavedFlight: keyboardShouldPersistTaps
      // lets this tap through with the keyboard still up. What the tap MEANS is
      // the caller's -- see onPress at the top of this file.
      onPress={() => onPress(r)}
    >
      <View style={s.routeFlatRowEdge} pointerEvents="none" />
      <View style={s.routeFlatBody}>
        {/* Identity and flags. Everything variable-width lives on this line so
            the times below keep the whole row to flex into; the airline is the
            only cell allowed to shrink, and may be absent entirely. */}
        <View style={s.routeFlatHead}>
          <View style={s.routeFlatIdent}>
            {airline !== null && (
              <Text style={s.routeFlatAirline} numberOfLines={1}>{airline}</Text>
            )}
            <Text style={s.routeFlatNumber} numberOfLines={1}>{leg.flight_number}</Text>
          </View>
          <View style={s.routeFlatTags}>
            {/* No "Direct" label: it printed identically on every row, and the
                note under the heading already says the whole list is direct.
                It earns a place here only once connections can appear. */}
            {!pinned && routeFastestKeys.has(routeRowKey(r)) && (
              <Text style={s.routeFastest}>{'fastest'}</Text>
            )}
            {risky && (
              <Text style={s.routeClosing} numberOfLines={1}>{'closing'}</Text>
            )}
            {statusWord !== null && (
              // "departed" takes the live green the app already uses for a
              // flight under way; the other two words carry their own colour.
              <Text
                style={[s.routeFlatStatus, { color: getStatusColor(statusWord === 'departed' ? 'active' : statusWord) }]}
                numberOfLines={1}
              >
                {statusWord}
              </Text>
            )}
          </View>
        </View>

        {/* Both cells are the same fixed width, because every 24-hour time is
            exactly five characters. The connector is the only flexed element
            between them, so the gap either side of it is equal by construction
            rather than by tuning. */}
        <View style={s.routeFlatTop}>
          <Text style={s.routeFlatTime} numberOfLines={1}>
            {depZ.clock}
          </Text>
          <View style={s.routeConn}>
            {ms !== null && (
              <Text style={s.routeConnDur} numberOfLines={1}>{formatCountdown(ms)}</Text>
            )}
            <View style={s.routeConnLineRow}>
              <View style={s.routeConnLine} />
              <View style={s.routeConnHead} />
            </View>
          </View>
          {/* The iso is still preferred; the fallback is the only thing that
              changes. A row with neither value gets the dash, which occupies
              the same 60pt cell a time does, so the arrival still ends on the
              row's right edge and the connector's share is unchanged. */}
          <Text style={[s.routeFlatTime, s.routeFlatTimeEnd]} numberOfLines={1}>
            {arrZ.clock}
          </Text>
        </View>

        {/* Its own row, repeating routeFlatTop's geometry exactly, so each code
            sits under its own time. Putting them INSIDE routeFlatTop would have
            grown the box the connector centres itself in, dragging the line
            below the times it belongs to. */}
        <View style={s.routeFlatCodes}>
          {/* THE ZONE BESIDE THE CODE, which is where a reader looks to ask
              "whose time is this". minWidth rather than width on the cell, so
              a long "GMT+5:30" takes from the spacer and not from the code. */}
          <Text style={s.routeFlatCode} numberOfLines={1}>
            {origin}
            {depZ.zone !== null && <Text style={s.routeFlatZone}>{` ${depZ.zone}`}</Text>}
          </Text>
          <View style={s.routeConnSpacer} />
          <Text style={[s.routeFlatCode, s.routeFlatCodeEnd]} numberOfLines={1}>
            {/* Never null in practice — a recovered row carries the code its
                name resolved to — but the wire type allows it, and the answer
                is knowable anyway: every row here is for this destination. */}
            {destination}
            {arrZ.zone !== null && <Text style={s.routeFlatZone}>{` ${arrZ.zone}`}</Text>}
          </Text>
        </View>

        {/* THE PHONE'S TIME, a size down, only for an end whose zone is not
            the phone's. A row where neither differs draws nothing here. */}
        {(depZ.yours !== null || arrZ.yours !== null) && (
          <View style={s.routeFlatCodes}>
            <Text style={s.routeFlatYours} numberOfLines={1}>{depZ.yours ?? ''}</Text>
            <View style={s.routeConnSpacer} />
            <Text style={[s.routeFlatYours, s.routeFlatCodeEnd]} numberOfLines={1}>{arrZ.yours ?? ''}</Text>
          </View>
        )}

        {/* THE LINE THAT SAYS WHY, under the codes, in the same amber as the
            tag. One sentence, so it is read rather than noticed. */}
        {risky && (
          <Text style={s.routeClosingNote}>{CATCH_RISKY_NOTE}</Text>
        )}
      </View>

      {/* Nested Touchable: React Native gives the responder to the deepest view
          that claims it, so this never triggers the row's own onPress. */}
      <TouchableOpacity
        style={s.routeFlatMark}
        activeOpacity={0.7}
        disabled={saved || busy}
        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        onPress={() => saveFromRoute(leg.flight_number, rowDay ?? rowDate, origin || null)}
      >
        <View style={s.routeFlatMarkBox}>
          {pending ? (
            <ActivityIndicator size="small" color="rgba(226,226,226,0.5)" />
          ) : (
            <Svg width={18} height={18} viewBox="0 0 24 24">
              <Path
                d="M6 3h12a1 1 0 0 1 1 1v17l-7-5-7 5V4a1 1 0 0 1 1-1z"
                fill={saved ? '#4ade80' : 'none'}
                stroke={saved
                  ? '#4ade80'
                  : busy ? 'rgba(226,226,226,0.25)' : 'rgba(226,226,226,0.5)'}
                strokeWidth={1.75}
              />
            </Svg>
          )}
        </View>
      </TouchableOpacity>
    </TouchableOpacity>
  );
}

// THE ROW'S OWN STYLES, EXACTLY AS THEY WERE IN THE SEARCH SCREEN'S SHEET.
const s = StyleSheet.create({
  // Flat rows. Separation is the file's existing hairline, the same one sf.row
  // and ir.row use; the breathing room comes from paddingVertical, not a box.
  // The same card as a saved row, and the same padding, which is what keeps the
  // times in their columns. See CARD_PAD.
  routeFlatRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 18,
    paddingHorizontal: CARD_PAD,
    backgroundColor: CARD_FILL,
    borderRadius: CARD_RADIUS, borderCurve: 'continuous',
    marginBottom: CARD_GAP,
  },
  // ── THE HAIRLINE, AS A SIBLING ──
  //
  // g.sheetEdge's PATTERN, not a border on the surface itself, and lib/glass.tsx
  // states why at SHEET_EDGE: React Native draws a border from the layer's own
  // radius as one unbroken rounded rectangle ONLY while all four sides share a
  // colour, and a border on the surface would also inset its content box by 1pt
  // on every side. An absolutely positioned sibling at the same radius costs no
  // layout and cannot split a corner arc.
  //
  // WHY THE SURFACE NEEDED ONE AT ALL: at 4.5% white on a near-black page a fill
  // alone barely registers, which is what made these read as text on the page
  // rather than as cards. One pixel of 10% white is what turns a tint into a
  // shape. See the elevation scale in lib/cards.ts.
  routeFlatRowEdge: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    borderWidth: 1, borderColor: SURFACE_EDGE, borderRadius: CARD_RADIUS, borderCurve: 'continuous',
  },
  // See routeLastKey. The hidden-count and truncation notes below the list keep
  // their own spacing, so dropping the gap leaves nothing touching.
  routeFlatRowLast: { marginBottom: 0 },
  routeFlatBody: { flex: 1 },
  routeFlatHead: { flexDirection: "row", alignItems: "center" },
  routeFlatIdent: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  routeFlatAirline: { fontSize: 13, color: "rgba(226,226,226,0.6)", fontFamily: SANS, flexShrink: 1 },
  routeFlatNumber: { fontSize: 13, color: "rgba(226,226,226,0.52)", fontFamily: MONO },
  // Content-width, never reserved: these are flags, and a fixed cell for a
  // status that almost never renders would leave a permanent hole. The identity
  // group flexes, so nothing here can push the row wider than the screen.
  routeFlatTags: { flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 0 },
  // No width: the cell that collided with the duration was 62pt against a 63.9pt
  // "scheduled" once letterSpacing was counted. Sized to content, it cannot.
  routeFlatStatus: { fontSize: 11, fontFamily: MONO_BOLD, letterSpacing: 0.5 },
  // No width of any kind. As a stretched child of the column body this spans the
  // full row, so the departure sits on the row's left edge and the arrival on its
  // right edge — the same right edge line one's flags end at. Constraining this
  // width was what left the arrival floating mid-row.
  // marginTop clears the duration, which hangs above the connector line without
  // taking layout height.
  routeFlatTop: { flexDirection: "row", alignItems: "center", marginTop: 14 },
  // minWidth, not width: a five-character 24-hour time fits exactly, so both
  // cells match and the connector is centred. Should a row ever fall back to a
  // backend-formatted string, the cell grows and the connector yields instead of
  // the time truncating.
  routeFlatTime: { fontSize: 20, color: "#ffffff", fontFamily: MONO_BOLD, minWidth: 60 },
  routeFlatTimeEnd: { textAlign: "right" },
  // The box spans everything between the times; alignItems centres the drawn
  // line inside it, so the gap either side is equal at every width.
  routeConn: { flex: 1, justifyContent: "center", alignItems: "center", marginHorizontal: 12 },
  // Absolutely positioned so it labels the line without adding row height or
  // shifting the line off the times' vertical centre.
  // MONO_BOLD at 0.75 rather than MONO at 0.4. It labels the connector it sits
  // on, and at 0.4 it read as a watermark rather than as the block time.
  routeConnDur: {
    position: "absolute", left: 0, right: 0, bottom: 7,
    fontSize: 11, color: "rgba(226,226,226,0.75)", fontFamily: MONO_BOLD, textAlign: "center",
  },
  routeConnLineRow: {
    flexDirection: "row", alignItems: "center",
    width: "100%", maxWidth: ROUTE_CONNECTOR_MAX,
  },
  routeConnLine: { flex: 1, height: 1, backgroundColor: "rgba(226,226,226,0.45)" },
  // Two borders of a square turned 45 degrees: an arrowhead with no SVG.
  routeConnHead: {
    width: 5, height: 5,
    borderTopWidth: 1, borderRightWidth: 1,
    borderColor: "rgba(226,226,226,0.45)",
    transform: [{ rotate: "45deg" }],
    marginLeft: -1,
  },
  // 60pt each end and a flexed middle with the same 12pt margins routeConn
  // carries, so a code lands directly under its own time at every width. The
  // times themselves are untouched: departures still start on the row's left
  // edge and arrivals still end on its right.
  routeFlatCodes: { flexDirection: "row", alignItems: "center", marginTop: 2 },
  routeFlatCode: {
    fontSize: 11, color: "rgba(226,226,226,0.52)", fontFamily: MONO, minWidth: 60,
  },
  routeFlatCodeEnd: { textAlign: "right" },
  // A CONNECTION'S OWN PARTS. The hub and wait take the connector's place in
  // the codes row, centred between the two codes; the transfer label is the
  // codes' grey with its first words in the one warning amber this row uses.
  viaMid: {
    flex: 1, marginHorizontal: 12, textAlign: "center",
    fontSize: 11, color: "rgba(226,226,226,0.75)", fontFamily: MONO_BOLD,
  },
  viaOvernight: { fontSize: 11, fontFamily: MONO_BOLD, color: "rgba(226,226,226,0.6)", letterSpacing: 0.5 },
  viaTransfer: { marginTop: 10, fontSize: 11, lineHeight: 15, color: "rgba(226,226,226,0.52)", fontFamily: SANS },
  viaTransferHead: { color: CD_LATE, fontFamily: MONO_BOLD },
  // The zone beside a code, and the phone's time on the line under: the codes'
  // own grey, the second a size down.
  routeFlatZone: { fontSize: 10 },
  routeFlatYours: {
    fontSize: 10, color: "rgba(226,226,226,0.52)", fontFamily: MONO, minWidth: 60,
  },
  routeConnSpacer: { flex: 1, marginHorizontal: 12 },

  // Icon only, no container. hitSlop carries the tap target.
  routeFlatMark: { marginLeft: 14 },
  routeFlatMarkBox: { width: 20, height: 20, alignItems: "center", justifyContent: "center" },
  // Its own size and family: it sits in the row's flag group, not inside a
  // parent Text it could inherit from.
  routeFastest: { fontSize: 11, color: "#4ade80", fontFamily: MONO },
  // THE RISKY BAND'S MARK, in the amber the app already uses for late. Same
  // size and family as the fastest tag it sits beside.
  routeClosing: { fontSize: 11, color: CD_LATE, fontFamily: MONO },
  // Its reason, one line under the codes, at the codes' size.
  routeClosingNote: { fontSize: 11, color: CD_LATE, fontFamily: SANS, marginTop: 8, lineHeight: 15 },
});

// ── A CONNECTION: TWO FLIGHTS, ONE ROW ──────────────────────────────────────
//
// THE SAME ROW AS A DIRECT ONE WHERE IT CAN BE. The two big clocks are the
// journey's ends -- the first leg's departure and the last leg's arrival --
// and the line between them carries the WHOLE journey time, so a connection and
// a direct flight compare at a glance. What differs is said where the eye
// already goes: the two flight numbers in the header, "via BLR · 1h 00m" under
// the line, and the transfer label under that.
//
// THE LABEL IS NEVER HIDDEN (§8 of docs/connection-search.md). Whether a bag is
// checked through decides whether the itinerary is usable at all, and somebody
// who learns it at the transfer desk was told by this row that it was fine.
function ViaRow({ r, pinned, onPress }: { r: RouteItinerary; pinned: boolean; onPress: (r: RouteOption) => void }) {
  const {
    savedFlights, routeResult, routeRowKey, routeLastKey,
    routeFastestKeys, routeSavingKey, saveItinerary, disownItinerary, routeCatchOf,
  } = useRouteResults();
  const first = optFirst(r);
  const last = optLast(r);
  const origin = legOrigin(first, routeResult?.origin ?? '');
  const destination = last.destination_iata ?? routeResult?.destination ?? '';
  const depZ = boardClock(first.departure_scheduled_iso, first.departure_scheduled, origin || null);
  const arrZ = boardClock(
    last.arrival_scheduled_iso,
    last.arrival_scheduled === null ? ROUTE_NO_TIME : stripZoneLabel(last.arrival_scheduled),
    destination || null,
  );
  const total = optDurationMs(r);
  const wait = optLayoverMs(r);
  // THE AIRLINE WHEN BOTH LEGS SHARE ONE, which is the case that reads as a
  // single journey; two carriers print as their two numbers and nothing more.
  const sameCarrier = r.transfer === 'same_carrier';
  const airline = sameCarrier ? airlineFromFlightNumber(first.flight_number) : null;
  // SAVED MEANS BOTH LEGS ARE, on their own days, watched or owned. OWNED MEANS
  // BOTH ARE IN MY FLIGHTS AS ONE TRIP -- the same trip id on each.
  const legRecords = r.legs.map(l => savedFlights.find(f => f.id === makeFlightId(l.flight_number, routeDayOf(l))));
  const saved = legRecords.every(f => f !== undefined);
  const owned = saved && legRecords[0]?.tripId != null && legRecords.every(f => f?.tripId === legRecords[0]?.tripId);
  const key = optKey(r);
  const pending = routeSavingKey === key;
  const busy = routeSavingKey !== null;
  const risky = routeCatchOf(r) === 'risky';
  // ── THE LONG PRESS: MY FLIGHTS ────────────────────────────────────────────
  //
  // THE BOOKMARK WATCHES; THIS IS FOR TAKING THE CONNECTION. The same split the
  // flight card makes -- its bookmark saves, its long-press menu offers "Add to
  // My Flights" -- here with the native sheet the app's other menus use. Adding
  // saves both legs as one owned trip; removing sends both back to the
  // watchlist and unsaves nothing.
  const openMenu = () => {
    if (busy) return;
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: `${first.flight_number} + ${last.flight_number} via ${r.hub}`,
        message: owned
          ? 'Both flights are in My Flights as one trip.'
          : 'Saves both flights to My Flights as one trip.',
        options: [owned ? 'Remove from My Flights' : 'Add to My Flights', 'Cancel'],
        destructiveButtonIndex: owned ? 0 : undefined,
        cancelButtonIndex: 1,
      },
      index => {
        if (index !== 0) return;
        if (owned) void disownItinerary(r);
        else void saveItinerary(r, true);
      },
    );
  };
  return (
    <TouchableOpacity
      style={[s.routeFlatRow, routeRowKey(r) === routeLastKey && s.routeFlatRowLast]}
      activeOpacity={0.7}
      onPress={() => onPress(r)}
      onLongPress={openMenu}
    >
      <View style={s.routeFlatRowEdge} pointerEvents="none" />
      <View style={s.routeFlatBody}>
        <View style={s.routeFlatHead}>
          <View style={s.routeFlatIdent}>
            {airline !== null && (
              <Text style={s.routeFlatAirline} numberOfLines={1}>{airline}</Text>
            )}
            <Text style={s.routeFlatNumber} numberOfLines={1}>
              {`${first.flight_number} + ${last.flight_number}`}
            </Text>
          </View>
          <View style={s.routeFlatTags}>
            {!pinned && routeFastestKeys.has(routeRowKey(r)) && (
              <Text style={s.routeFastest}>{'fastest'}</Text>
            )}
            {risky && (
              <Text style={s.routeClosing} numberOfLines={1}>{'closing'}</Text>
            )}
            {r.overnight && (
              <Text style={s.viaOvernight} numberOfLines={1}>{'overnight'}</Text>
            )}
          </View>
        </View>

        <View style={s.routeFlatTop}>
          <Text style={s.routeFlatTime} numberOfLines={1}>{depZ.clock}</Text>
          <View style={s.routeConn}>
            {total !== null && (
              <Text style={s.routeConnDur} numberOfLines={1}>{formatCountdown(total)}</Text>
            )}
            <View style={s.routeConnLineRow}>
              <View style={s.routeConnLine} />
              <View style={s.routeConnHead} />
            </View>
          </View>
          <Text style={[s.routeFlatTime, s.routeFlatTimeEnd]} numberOfLines={1}>{arrZ.clock}</Text>
        </View>

        <View style={s.routeFlatCodes}>
          <Text style={s.routeFlatCode} numberOfLines={1}>
            {origin}
            {depZ.zone !== null && <Text style={s.routeFlatZone}>{` ${depZ.zone}`}</Text>}
          </Text>
          {/* THE HUB AND THE WAIT, under the line the journey time sits on. */}
          <Text style={s.viaMid} numberOfLines={1}>
            {`via ${r.hub}${wait !== null && wait >= 0 ? ` · ${formatCountdown(wait)}` : ''}`}
          </Text>
          <Text style={[s.routeFlatCode, s.routeFlatCodeEnd]} numberOfLines={1}>
            {destination}
            {arrZ.zone !== null && <Text style={s.routeFlatZone}>{` ${arrZ.zone}`}</Text>}
          </Text>
        </View>

        {(depZ.yours !== null || arrZ.yours !== null) && (
          <View style={s.routeFlatCodes}>
            <Text style={s.routeFlatYours} numberOfLines={1}>{depZ.yours ?? ''}</Text>
            <View style={s.routeConnSpacer} />
            <Text style={[s.routeFlatYours, s.routeFlatCodeEnd]} numberOfLines={1}>{arrZ.yours ?? ''}</Text>
          </View>
        )}

        <Text style={s.viaTransfer} numberOfLines={2}>
          <Text style={s.viaTransferHead}>{TRANSFER_LABEL[r.transfer]}</Text>
          {`  ${TRANSFER_NOTE[r.transfer]}`}
        </Text>

        {risky && (
          <Text style={s.routeClosingNote}>{CATCH_RISKY_NOTE}</Text>
        )}
      </View>

      {/* BOTH LEGS, WATCHED, as a direct row's bookmark watches one flight. See
          saveItinerary: both are looked up first, and nothing is written unless
          both can be. Owning the pair is the long press. */}
      <TouchableOpacity
        style={s.routeFlatMark}
        activeOpacity={0.7}
        disabled={saved || busy}
        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        onPress={() => saveItinerary(r, false)}
      >
        <View style={s.routeFlatMarkBox}>
          {pending ? (
            <ActivityIndicator size="small" color="rgba(226,226,226,0.5)" />
          ) : (
            <Svg width={18} height={18} viewBox="0 0 24 24">
              <Path
                d="M6 3h12a1 1 0 0 1 1 1v17l-7-5-7 5V4a1 1 0 0 1 1-1z"
                fill={saved ? '#4ade80' : 'none'}
                stroke={saved
                  ? '#4ade80'
                  : busy ? 'rgba(226,226,226,0.25)' : 'rgba(226,226,226,0.5)'}
                strokeWidth={1.75}
              />
            </Svg>
          )}
        </View>
      </TouchableOpacity>
    </TouchableOpacity>
  );
}
