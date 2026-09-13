// ── THE GMAIL PULL, AND IT IS NO LONGER A SECTION ON HOME ───────────────────
//
// IT WAS A ROW AT THE TOP OF THE WATCHLIST and it had outgrown that. A pull is
// how a booking becomes a JOURNEY -- autoAdd owns every leg it resolves, which
// puts them on My Flights and not on the list the row sat above -- so the
// control was on the one screen its results never appear on. Home is the
// watchlist; this belongs where the trips are, and to anyone else who asks.
//
// A PROVIDER, MOUNTED ONCE, AND IT WAS BRIEFLY A HOOK PER SCREEN. The state is
// the RUN's rather than a screen's: a pull started from the search screen is the
// same pull My Flights is showing the state of, and two hooks meant the panel
// there could read "add flights from gmail" while a run it could not see was
// already in flight. One provider is one answer to "is a pull happening", which
// is the only honest number of answers to that question.
//
// THE TWO PRESENTATIONS ARE STILL TWO. My Flights reads `label` and `state` for
// its panel; the search screen reads neither and takes the sentence `pull`
// returns. Sharing the state does not merge the surfaces -- it stops them
// disagreeing about the one fact underneath both.
//
// EVERYTHING IT NEEDS IS ON A CONTEXT. The session, the saved list, the two
// banners and the sign-in are all reachable from anywhere inside the providers
// app/_layout.tsx mounts, so no screen has to thread anything in. That is the
// same reason lib/googleAuth.tsx is a hook rather than a prop.
import { createContext, useContext, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';
import { useAccount } from './account';
import { useSaved, useAccountChange, API_BASE } from './saved';
import { useToast } from './toast';
import { useGoogleSignIn } from './googleAuth';
import { SavedFlight, savedFlightFromApi } from './storage';
import { pendingFromLeg } from './pendingRules';
import { routeDateLabel } from './flightstatus';

// ── A LEG READ OUT OF GMAIL ─────────────────────────────────────────────────
//
// WHAT /gmail/flights RETURNS, one per flight leg, already re-checked by the
// server: the number matches a flight-number regex that accepts 6E, the date
// is YYYY-MM-DD and not in the past, the PNR is a short code and never a
// ticket number. Nothing here is the email itself -- `source` is the subject
// and the received date, and that is deliberately all the app is given.
export type GmailLeg = {
  flight_number: string;
  date: string;
  departure_time: string | null;
  origin: string | null;
  origin_name: string | null;
  destination: string | null;
  destination_name: string | null;
  airline: string | null;
  // CODESHARES. The booking prints the marketing number; the aircraft flies
  // under the operator's. When the email printed the operator's number it is
  // here, and the lookup is made under it -- that is the number the landing
  // feed knows. When it did not, the provider resolves the marketing number to
  // the operating flight itself, so the lookup still lands on the right one.
  operated_by: string | null;
  operating_flight_number: string | null;
  pnr: string | null;
  confidence: number;
  // WHETHER THE AIRLINE HAS CALLED IT OFF. The extractor classifies each email
  // and marks every leg a cancellation notice names. OPTIONAL: a server that
  // predates the classifier sends no such field, and absent means scheduled.
  leg_status?: 'scheduled' | 'cancelled' | null;
  // WHEN THE BOOKING SAID IT LANDS, where the email printed it. The date is
  // separate because an overnight leg lands on another day, and is absent when
  // the email gave one date for the whole leg. Both optional: the extractor is
  // told never to compute an arrival, so an email that prints none returns
  // none. See the pending leg type for what they are for.
  arrival_time?: string | null;
  arrival_date?: string | null;
  source: { subject: string | null; received: string | null };
};

export type GmailPull = {
  status: 'idle' | 'loading' | 'done' | 'error';
  flights: GmailLeg[];
  message: string;
};
export const IDLE_PULL: GmailPull = { status: 'idle', flights: [], message: '' };

// ── WHAT A PULL ENDED UP BEING ──────────────────────────────────────────────
//
// A SENTENCE IN EVERY CASE, because the search screen has nowhere else to put
// the answer: it has no row to relabel, only the response area, and a pull that
// printed nothing there would read as a press that did nothing.
//
// THE TOASTS AND THE UNDO BANNER STILL FIRE. They are not a duplicate of this:
// the banner is the only way to undo an add, and it is raised while the pull is
// still the thing on screen. This is what a CALLER can say about the run
// afterwards, in its own surface.
export type PullOutcome = {
  kind: 'signin' | 'error' | 'done' | 'busy';
  message: string;
};

// ── ONE RUN AT A TIME, ACROSS EVERY CONSUMER ────────────────────────────────
//
// MODULE SCOPE, NOT STATE, because the thing being protected is not a screen's
// display -- it is the WRITES. Two pulls in flight look up the same legs and
// race to own them, and ownFlight's cap and the pending queue's duplicate test
// would both be answered against a list the other run had not finished
// changing. The same reasoning and the same shape as backfillRunning in
// lib/watch.ts.
let pullRunning = false;

// ── ASKING FOR A GMAIL IMPORT IN WORDS ──────────────────────────────────────
//
// LOCAL AND FREE, AND IT SITS ABOVE THE MODEL RUNGS. "pull my flights from
// gmail" used to reach /parse, which looked for two airports in it, found
// none, and answered "I did not catch where you are flying from" -- a unit
// spent to misread a sentence the app could have recognised for nothing.
//
// A SOURCE AND THEN A REASON TO BELIEVE IT, which is what keeps this off
// ordinary questions. The source word alone is not enough: "check my email"
// names one and is not an import request. So either the verb is unambiguous --
// pull, import, sync, fetch, all of which mean "bring it here" and nothing
// else -- or a weaker verb has to be carrying an OBJECT this app deals in.
//
// MEASURED AGAINST THE ELEVEN NON-SEARCH INPUTS nlLooksLikeSearch WAS TUNED ON
// -- "is my flight on time", "what time does my flight land", "how do I get to
// the airport", "what is my gate", "cancel my booking" and the rest: none of
// them names a mail source, so none of them reaches this at all.
//
// UNDER-REACHING IS THE FAILURE THIS PREFERS. A phrasing it does not know
// falls through to where it already went, which is a visible answer from the
// model rather than an invisible wrong one from here.
const GMAIL_SOURCE = /\b(g-?mail|e-?mail|inbox|mailbox|mail)\b/;
const GMAIL_STRONG = /\b(pull|pulling|import|importing|sync|syncing|fetch|fetching)\b/;
const GMAIL_WEAK = /\b(get|grab|load|read|scan|check|find|add|show|bring)\b/;
const GMAIL_OBJECT = /\b(flight|flights|trip|trips|booking|bookings|ticket|tickets|itinerary|itineraries|reservation|reservations|journey|journeys)\b/;

export function looksLikeGmailImport(q: string): boolean {
  const s = q.toLowerCase();
  if (!GMAIL_SOURCE.test(s)) return false;
  if (GMAIL_STRONG.test(s)) return true;
  return GMAIL_WEAK.test(s) && GMAIL_OBJECT.test(s);
}

type GmailPullValue = {
  state: GmailPull;
  // THE FOUR STATES, SPELT ONCE. It is the label Home's row carried, and it is
  // computed here rather than by each screen so two controls for one action
  // cannot come to describe it differently. The session is read here too,
  // which is what keeps a consumer from having to import lib/account for a
  // string.
  label: string;
  pull: () => Promise<PullOutcome>;
  reset: () => void;
};

const GmailPullContext = createContext<GmailPullValue | null>(null);

export function GmailPullProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GmailPull>(IDLE_PULL);
  const { session, persistSession } = useAccount();
  const { savedFlights, ownFlight, handleUnsave, addPendingLeg, retryPending } = useSaved();
  const { showToast, showUndo } = useToast();
  const { signIn } = useGoogleSignIn();

  // THE RESET THAT USED TO BE A LINE IN HOME'S ACCOUNT WATCH. A pull's result
  // belongs to the account it was read from, so signing in or out empties it --
  // and now every consumer gets that for free rather than each remembering.
  useAccountChange(() => { setState(IDLE_PULL); });

  // ── AUTO-ADD, WITH ONE UNDO FOR THE LOT ──────────────────────────────────
  //
  // EVERY COMPARABLE APP EITHER CONFIRMS OR OFFERS AN UNDO, and this offers the
  // undo: the legs are saved as they come, the banner names what was added,
  // and undo removes exactly those and nothing else. Not a confirmation
  // screen, not silent.
  //
  // EACH LEG IS LOOKED UP FIRST, under its date and origin, because a saved
  // record is a full DTO and the email gave a number and a day. That is one
  // provider unit per new leg -- two to six per pull -- and it is spent only
  // on legs not already on the watchlist.
  //
  // THE LOOKUP NUMBER IS THE OPERATING ONE WHERE THE EMAIL PRINTED IT. Where
  // it did not, the marketing number goes up and the provider answers with the
  // operating flight anyway, so the record that comes back is the one the
  // aircraft actually flies under. The id is built from THAT, which is why the
  // "already saved" test is made on the looked-up record and not on the leg.
  //
  // IT RETURNS THE SENTENCE IT REPORTED. Every branch already computed a line
  // for a toast or for the banner; handing it back is what lets a caller with
  // no banner say the same thing in its own surface.
  const autoAdd = async (legs: GmailLeg[]): Promise<string> => {
    const added: SavedFlight[] = [];
    let queued = 0;
    // Legs a save refused. Counted rather than inferred from the arithmetic,
    // because legs also leave this loop by being queued or already present, and
    // "how many were turned away" is a different question from "how many are
    // missing".
    let skipped = 0;
    // EVERY WAY A LEG CAN BE TURNED AWAY, COUNTED BY NAME. The queue used to
    // report only its successes -- `if (r === 'added')` and nothing else -- so a
    // duplicate, a full queue and a past date all vanished identically. That is
    // what lost the second and third legs of a real booking: the queue was at
    // its old cap of ten and refused them in silence.
    const refused: Record<'dup' | 'limit' | 'past', number> = { dup: 0, limit: 0, past: 0 };
    const tried: string[] = [];
    for (const leg of legs) {
      // THE OPERATING NUMBER FIRST, THEN THE MARKETING ONE. An email that
      // printed "operated as AA 100" may have printed it wrongly, or the
      // provider may file the flight under the marketing number only; a miss
      // on the first costs one unit and the second still finds it.
      const numbers = leg.operating_flight_number !== null && leg.operating_flight_number !== leg.flight_number
        ? [leg.operating_flight_number, leg.flight_number]
        : [leg.flight_number];
      try {
        const q = [`date=${encodeURIComponent(leg.date)}`];
        if (leg.origin !== null) q.push(`origin=${encodeURIComponent(leg.origin)}`);
        let data: any = null;
        for (const number of numbers) {
          const resp = await fetch(`${API_BASE}/flight/${encodeURIComponent(number)}?${q.join('&')}`);
          const body = await resp.json();
          if (resp.ok && !body.error) { data = body; break; }
        }
        if (data === null) {
          // NOT IN THE SCHEDULE YET. Kept on the device with what the email
          // said, shown as such, and looked up again on every pull and once a
          // day until the airline publishes it. See lib/pendingRules.ts.
          const r = await addPendingLeg(pendingFromLeg(leg, Date.now()));
          if (r === 'added') queued += 1;
          else refused[r] += 1;
          tried.push(pendingFromLeg(leg, Date.now()).id);
          continue;
        }
        // THE EMAIL'S OWN FACTS, WHICH THE PROVIDER NEVER RETURNS. A PNR
        // belongs to the airline's reservation system rather than to the
        // flight, and the operating number is what the booking printed. Both
        // used to live only in the pull's result list; that list was a
        // duplicate and was deleted, so they are written onto the record here
        // and touchSavedFlight carries them through every later refresh.
        const record: SavedFlight = {
          ...savedFlightFromApi(data),
          pnr: leg.pnr,
          operatingFlightNumber:
            leg.operating_flight_number !== null && leg.operating_flight_number !== leg.flight_number
              ? leg.operating_flight_number
              : null,
          operatedBy: leg.operated_by,
        };
        if (savedFlights.some(f => f.id === record.id) || added.some(f => f.id === record.id)) continue;
        // ── OWNED, NOT WATCHED ────────────────────────────────────────
        //
        // A BOOKING IN YOUR OWN INBOX IS YOUR OWN TRIP. Saving these to the
        // watchlist made every leg a thing the person was following rather than
        // a thing they were on, so a three-leg itinerary arrived as three
        // unrelated rows and the connection detection never saw them. Owning
        // runs that detection, folds the legs into one journey, merges two
        // journeys when a leg bridges them, and tells the server the person is
        // ON the flight -- which is what decides whether a notification says
        // "your flight to Delhi" or "the flight from Mumbai".
        //
        // THE RARE CASE IS ACCEPTED AND NOT DETECTED. A flight forwarded so you
        // can meet someone lands here as owned and is wrong, and nothing in an
        // email distinguishes the two. Moving it back is one swipe; guessing
        // would be wrong more often than the case is common.
        //
        // capped: A PULL RESPECTS THE TWENTY, where owning by hand does not. An
        // inbox is not one deliberate act, and a year of mail quietly filling
        // the app past its cap is worse than a pull that stops and says so.
        //
        // remind: false. Owning one flight by hand means "I am flying this" and
        // reminders follow from that statement; a bulk import makes no such
        // statement about any single leg. Six reminders nobody asked for is how
        // somebody turns notifications off altogether.
        const outcome = await ownFlight(record, undefined, { capped: true, remind: false });
        if (!outcome.ok) {
          // SKIPPED, NOT THE END OF THE PULL. This used to break, which cost
          // more than the refused leg: a booking of three legs lost the second
          // to the ceiling and the third was never attempted at all. It also
          // cost the pending path, because a leg the provider cannot resolve
          // never reaches a save and would have queued happily.
          skipped += 1;
          continue;
        }
        added.push(record);
      } catch {
        // One leg that will not look up is skipped; the rest still go in.
      }
    }
    // THE PENDING LEGS THIS PULL DID NOT SEE -- an email older than the window,
    // say -- get their retry now too, and anything that resolves joins the
    // banner as an addition, because to the user that is what it is.
    const retry = await retryPending('pull', tried);
    for (const r of retry.resolved) added.push(r);

    // ── WHAT WAS TURNED AWAY, WHEREVER IT WAS TURNED AWAY ──────────────────
    //
    // ALWAYS LOGGED, so a development build can see the breakdown even when the
    // banner has room for only a number. A refusal that is counted but never
    // named is the same failure one layer along.
    const refusedTotal = refused.dup + refused.limit + refused.past;
    if (refusedTotal > 0 || skipped > 0) {
      console.warn(
        `[pull] legs=${legs.length} added=${added.length} queued=${queued}`
        + ` | not saved=${skipped}`
        + ` | not queued=${refusedTotal} (duplicate=${refused.dup},`
        + ` queue full=${refused.limit}, past-dated=${refused.past})`,
      );
    }
    // A DUPLICATE IS NOT A LOSS AND IS NOT COUNTED AS ONE. The leg is already in
    // the queue, which is the state the person wanted; saying "1 skipped" for it
    // would report a problem that does not exist. Only the two refusals that
    // lose a leg are surfaced.
    const lost = skipped + refused.limit + refused.past;
    // ── THE REASON, NOT JUST THE COUNT ──────────────────────────────────────
    //
    // "2 skipped" SENT SOMEBODY TO READ A CONSOLE. The breakdown was logged and
    // the banner showed a bare number, so the one visible message named a
    // problem without naming which problem, and the only way to find out was a
    // terminal. The reasons need different actions -- a full queue is fixed by
    // forgetting a leg, a past date cannot be fixed at all -- so the count on
    // its own is not actionable.
    //
    // THE DOMINANT ONE WINS, because the banner fits about 26 characters and a
    // pull that hits two different walls at once is not worth the words. The
    // full breakdown is still in the log for the case where it matters.
    const lostWhy = refused.past > 0 ? 'past-dated'
      : refused.limit > 0 ? 'queue full'
      : skipped > 0 ? 'not saved'
      : '';

    if (added.length === 0) {
      // THE CAP'S MESSAGE NAMES THE RIGHT PLACE NOW. These legs go to My
      // Flights, so "watchlist limit" would send somebody to look at the wrong
      // screen for something to remove. Twenty is the number in both, because
      // it is one store.
      // THE ONLY PLACE A TOAST IS VISIBLE FOR THIS, because nothing was added
      // so there is no undo banner to be covered by. Named rather than generic:
      // a full queue is something the person can act on by forgetting old
      // entries, and a past date is not.
      const none = refused.limit > 0 ? 'the pending list is full — forget one'
        : lost > 0 ? `${lost} flight${lost === 1 ? '' : 's'}: ${lostWhy}`
        : queued > 0 ? (queued === 1 ? '1 flight not in the schedule yet' : `${queued} flights not in the schedule yet`)
        : legs.length > 0 ? 'already in My Flights'
        : 'no upcoming flights found in your gmail';
      showToast(none);
      return none;
    }
    // WITHIN THE BANNER'S 26 CHARACTERS: "added 6E5071 · 14 Sep" is 21, and
    // "added 6E5071 +2 more" is 20 at the longest number this app sees.
    // ── THE COUNT OF WHAT WAS TURNED AWAY GOES IN THE BANNER ────────────────
    //
    // NOT IN A TOAST BESIDE IT, and that is the bug this replaces rather than a
    // preference. showToast and showUndo draw at the SAME coordinates -- one
    // toastWrap, one top inset -- and the undo banner renders after the toast,
    // so it paints over it. The "some were not added" toast below was firing
    // correctly and was covered by the banner every time. A partial add looked
    // exactly like a complete one.
    //
    // SO THE ONE VISIBLE MESSAGE CARRIES BOTH FACTS. It stays inside the 26
    // characters the banner fits at 320pt: "added SK936 · 2 skipped" is 23.
    const first = added[0];
    const tail = lost > 0 ? ` · ${lost} ${lostWhy}` : '';
    const label = added.length === 1
      ? `added ${first.flightNumber}${tail || ` · ${routeDateLabel(first.flightDate).replace(/^\w+ /, '')}`}`
      : `added ${first.flightNumber} +${added.length - 1}${tail || ' more'}`;
    showUndo(label, async () => {
      for (const r of added) await handleUnsave(r);
      showToast(added.length === 1 ? `${first.flightNumber} removed` : `${added.length} flights removed`);
    });
    // NO SECOND MESSAGE HERE. It would be drawn under the banner above and
    // never seen; the banner's own label carries the count instead.
    return label;
  };

  // ── PULL FROM GMAIL ──────────────────────────────────────────────────────
  //
  // ONE PRESS, ONE REQUEST, A LIST. The server searches a year of received
  // mail, decodes the bodies, asks the model per email and re-checks every
  // leg; this sends the token and routes what comes back. Nothing is shown by
  // the pull itself -- every leg it resolves is OWNED, so it appears on My
  // Flights, and one it cannot resolve is queued and appears as an
  // unpublished leg inside its journey.
  //
  // THE SERVER'S `code` IS WHAT THIS SWITCHES ON, not the sentence beside it.
  // An expired or refused sign-in has to CLEAR the stored token, or the next
  // pull sends the same dead token again and gets the same answer for ever.
  const pull = async (): Promise<PullOutcome> => {
    if (pullRunning) return { kind: 'busy', message: 'already reading your gmail' };
    if (session === null) {
      // No session to send. On native the sign-in flow produces one; on web
      // the sign-in path never has, so this is honest about that and does not
      // pretend to try. A phone updated from the build that held a raw Google
      // token lands here too: signed in, no session, one tap away.
      if (Platform.OS === 'web') {
        const m = 'gmail pull needs the iphone app';
        showToast(m);
        return { kind: 'error', message: m };
      }
      signIn();
      return { kind: 'signin', message: 'sign in with google, then ask again' };
    }
    pullRunning = true;
    setState({ status: 'loading', flights: [], message: '' });
    try {
      const response = await fetch(`${API_BASE}/gmail/flights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session}` },
        body: JSON.stringify({}),
      });
      const data = await response.json() as {
        error?: string | null; code?: string | null; flights?: GmailLeg[];
      };
      if (data.code === 'gmail_expired' || data.code === 'gmail_forbidden') {
        await persistSession(null);
        const m = data.error || 'sign in again to pull from gmail';
        setState({ status: 'error', flights: [], message: m });
        showToast('google sign-in expired');
        return { kind: 'error', message: m };
      }
      if (data.error || !response.ok) {
        const m = data.error || 'could not read gmail';
        setState({ status: 'error', flights: [], message: m });
        return { kind: 'error', message: m };
      }
      const legs = data.flights ?? [];
      setState({ status: 'done', flights: legs, message: '' });
      // THE EMPTY CASE IS autoAdd'S TOO, so the sentence for it is written in
      // one place. It reports "no upcoming flights found in your gmail" and
      // nothing is added, which is exactly what an empty list means.
      return { kind: 'done', message: await autoAdd(legs) };
    } catch {
      const m = 'could not reach the server';
      setState({ status: 'error', flights: [], message: m });
      return { kind: 'error', message: m };
    } finally {
      pullRunning = false;
    }
  };

  const label =
    session === null ? 'reconnect gmail to pull flights'
    : state.status === 'loading' ? 'reading your gmail'
    : state.status === 'done' ? 'pull from gmail again'
    : 'add flights from gmail';

  // NOT MEMOISED, for the reason spelled out in lib/googleAuth.tsx: this
  // re-renders when its own state moves or when a store it reads does, and
  // every consumer already re-renders on the second of those.
  return (
    <GmailPullContext.Provider value={{ state, label, pull, reset: () => setState(IDLE_PULL) }}>
      {children}
    </GmailPullContext.Provider>
  );
}

// THE NAME My Flights AND THE SEARCH SCREEN ALREADY CALL, unchanged across the
// conversion: it was the implementation and is now the reader.
export function useGmailPull(): GmailPullValue {
  const v = useContext(GmailPullContext);
  if (v === null) throw new Error('useGmailPull must be called inside GmailPullProvider');
  return v;
}
