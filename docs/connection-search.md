# Connection search — Stage 2 plan

**Status:** Stage 1 is built and shipped (commit `f6175e4`). Stage 2 is not started.
This document is the plan it will be built from, and it exists mainly so the
licence constraint in §1 cannot be lost.

**Goal.** When a route search returns no direct flight — or few of them — offer
connecting itineraries through one hub, ranked by total journey time. No prices;
no provider in this app carries a fare.

---

## 1. The licence constraint, which is not a tuning parameter

**AeroDataBox confirmed that route data from the routes/daily endpoint is
*Contents* under their terms, not a *Derived Work*.** The question put to them
was whether reshaping that data — aggregating it into a hub map, discarding
fields, storing only the intersection — would make the result a Derived Work
and so exempt from the caching limit. It does not. It remains Contents however
it is reformatted, and the **seven-day caching ceiling applies to all of it**.

> The exact wording of their reply is not recorded here. If it matters for a
> future decision, retrieve it from the support thread rather than relying on
> this summary.

Two consequences:

1. **`ROUTE_LIST_CACHE_TTL = 6 days.`** Six is the ceiling with a day of margin
   for a slow refresh or a clock skew. **This number goes up only if the terms
   do.** Every other TTL in the route path was chosen against cost and
   staleness and can be argued about; this one was chosen against a contract
   and cannot. Seven removes the margin. Past seven is a breach.
2. **The shipped airport JSON must not be derived from AeroDataBox.** Baking
   route data into the app binary is a permanent cache and is plainly outside
   the seven days. Use OurAirports, which is public domain and is already the
   source for `lib/airports.ts` (1,223 airports) and `airport_icao.py` (4,017).

---

## 2. Cache TTLs

| Cache | TTL | Why |
|---|---|---|
| Route list (per airport) | **6 days** | §1. Contractual ceiling, not tuning. |
| Departure board — dated | 6–12 hours | Existing `ROUTE_FUTURE_CACHE_TTL` is 12h. |
| Departure board — rolling | 30 minutes | Existing `ROUTE_CACHE_TTL`. Unchanged. |
| Assembled itinerary results | 4 hours | Cheap to rebuild from cached boards. |

Everything except the route list was already inside the limit by accident of
cost tuning rather than by design. Say so in the code so nobody "simplifies"
one of them upward later.

---

## 3. Finding candidate hubs: the intersection

For a search **A → B**:

1. Fetch **A's route list** — every destination A flies to.
2. Fetch **B's route list** — every origin that flies to B. (The endpoint is
   per airport and returns destinations; B's destination list stands in for its
   origins, since scheduled service is near-symmetric. Note this assumption:
   it is not exactly true and is cheap to be wrong about.)
3. **Intersect them.** An airport in both lists is somewhere you can fly A → H
   and H → B. That set is the candidate hubs.

Each list is one call at 6 units, cached 6 days — so a search costs 0 or 12
units for this step depending on cache state.

**Rank the intersection by `averageDailyFlights`**, which the endpoint returns
per destination (LHR→JFK is 23.1/day, LHR→DUB 18.7). A hub with more daily
flights on both legs is likelier to yield a workable connection, and this is a
better ordering than anything we would infer ourselves.

The response also carries `countryCode` per destination, which feeds the
domestic/international test in §6 without a second source.

---

## 4. The detour-ratio prune

The intersection is too large to search — LHR alone has 212 destinations. Prune
by how far out of the way the hub is:

```
detour_ratio = (km(A→H) + km(H→B)) / km(A→B)
```

using the great-circle helper already in `lib/airports.ts` (`kmBetween`), and
the coordinates in the shipped airport JSON. Drop any hub above the threshold.

**The threshold is 1.4.** A ratio of 1.0 is a hub directly on the line; 1.4
admits a real dogleg — roughly a 40% longer journey than flying it straight —
while cutting the absurd, such as A → B via a hub on another continent. It was
chosen deliberately tighter than the 1.6 first proposed: a connection that adds
more than half again to the distance is rarely the itinerary anybody wants, and
a tight prune also cuts board calls, which is where the units go.

It remains the parameter most likely to want tuning once the search runs
against real routes. Tune it on evidence, not on taste, and record what the
evidence was.

Prune before spending any board calls. The whole point is that boards are the
expensive step and hubs are free to reject.

---

## 5. The cap and the spacing

- **At most 4 hubs per search**, taken from the pruned, frequency-ranked list.
- **At most 24 provider units per search** for the board calls, which is a hard
  stop rather than a target. A dated board is 4 units (two 12-hour windows), so
  4 hubs × 2 boards = 8 boards = 32 units would exceed it — the cap is what
  forces fewer hubs or reuse of an already-cached board.
- **`ROUTE_WINDOW_SPACING_SECONDS = 1.3` between board calls.** The provider
  returns 429 on back-to-back calls; this is measured, not guessed, and already
  in `mcp_server.py`.
- **One stop only.** Two-stop itineraries multiply the board cost and are not
  what this feature is for.
- **Opt-in.** A button in the results sheet, not an automatic search on every
  route lookup. Most searches have a direct flight and should cost nothing
  extra.

---

## 6. Layover minimums

A connection is only offered when the layover is workable:

| | Minimum | Maximum |
|---|---|---|
| Both legs within one country | **60 minutes** | 24 hours |
| Either leg crosses a border | **120 minutes** | 24 hours |

Domestic vs international is decided by the two airports' `countryCode`; an
airport whose country is unknown is treated as international, the stricter
reading. The 24-hour maximum is `MAX_CONNECTION_MS`, already in `lib/saved.tsx`
and mirrored as `MAX_LAYOVER_MS` in the trip screen.

**These minimums are an estimate and the code must say so.** No provider in
this app carries real minimum connection times. They do not account for
terminal changes, for the walk between two specific gates, or for whether the
traveller has bags. The same numbers are used by the connection-delay warning;
if one changes, both change.

---

## 7. Codeshare deduplication

The board call already sets `withCodeshared: "false"`, so a single board does
not return the same physical flight twice under two marketing numbers. That
does **not** solve it here: two *itineraries* can be the same journey when the
legs come from different boards.

The rule: **two itineraries are the same journey when both legs share a
departure instant and an airport pair.** Keep one and drop the other. Prefer
the one whose carrier matches the other leg's carrier, so a single-airline
itinerary is preferred over a mixed one that flies the same aircraft.

**When two itineraries differ only in marketing carrier and neither matches the
other leg, keep the alphabetically first.** Not because it is the better
flight — it is the same aircraft either way — but because the result has to be
stable between two searches of the same route, and alphabetical order is the
only tie-break available that does not depend on the order the provider
happened to return rows in. Say exactly that at the comparison, so nobody
later reads it as a quality judgement and "improves" it.

Related known defect: the provider mislabels at least one carrier — QP returns
as "Starlight Airline", not Akasa Air — which is why `RouteFlight` deliberately
omits `airline` from the rendered fields and the app reads the two-letter
prefix of the flight number instead. Any dedup rule that keys on the airline
*name* will be wrong for those carriers; key on the prefix.

---

## 8. Self-transfer labelling

An itinerary whose two legs are **not sold as one booking** leaves the
traveller responsible for the transfer: bags are not through-checked, and if
leg 1 is late nobody rebooks leg 2. This app assembles itineraries from two
independent boards, so **every itinerary it produces is a self-transfer unless
both legs are on the same carrier**, and even then it is not evidence of a
through-fare.

**Every itinerary carries a caveat, and the wording differs by case.** The app
assembled both of them out of two independent boards and cannot prove a
through-fare exists in either case, so saying nothing on a same-carrier
itinerary would imply a protection we have no evidence for. Two wordings
rather than one, because the two cases are genuinely different in how likely
the protection is:

| Case | Wording |
|---|---|
| Carriers differ | **Self-transfer** — *separate bookings; bags are not checked through and a delay is not protected.* |
| Same carrier | **Not a through-fare** — *Terminal built this connection; the airline may not sell it as one.* |

Both belong on the row, not in a detail view. Whether a bag is checked through
decides if the itinerary is usable at all, and a traveller who discovers it at
the transfer desk was told by us that it was fine.

> The two strings above are the wording to build from, not final copy. They are
> longer than the row currently has space for; Stage 3 settles the exact words
> against the rendered width. What is settled is that both cases speak, and
> that they do not say the same thing.

---

## 9. What Stage 1 already built

The wire shape and the accessors exist and are shipped. Stage 2 fills them in
rather than designing them:

```ts
export type RouteItinerary = {
  kind: 'via';
  legs: [RouteLeg, RouteLeg];   // in the order flown
  hub: string;                  // leg 1's destination, leg 2's origin
  overnight: boolean;           // leg 2 departs on a later local date
  international: boolean;       // either leg crosses a border
};
```

Also already present: `optKey`, `optDepIso`/`optArrIso`, `optDurationMs`,
`optLayoverMs`, `optCarriers`, `optLegsWithOrigin`, and `origin_iata` on every
board row so a second leg knows where it departs from. Every derivation in
`lib/routeResults.tsx` already reads through these, so an itinerary sorts,
filters and counts correctly the moment one is produced.

Not built: `RouteRow` returns `null` for a `'via'` option, and the sheet and
the map bubble render nothing for one. That is Stage 3.

---

## 10. Unit cost

| Item | Units | Note |
|---|---|---|
| Route list, one airport | **6** | Measured twice: IDR and LHR. Flat — does not scale with hub size (LHR returns 212 destinations for the same 6). |
| Dated board, one airport | 4 | Two 12-hour windows. |
| Rolling board, one airport | 2 | One window. |
| **Route lists per airport per month** | **30** | 5 refreshes at 6 days. Was 6/month at the old 30-day TTL. |

A realistic month for eight frequently searched airports: **~240 units, 0.6% of
the 40,000 monthly allowance.** The cost is paid per *distinct airport
searched*, not per search — a user searching the same five airports repeatedly
pays the same 150/month however often they search. The exposure is a user who
searches many different airports once each; if that needs bounding, cap the
number of cached route lists (LRU of ~40 airports) rather than capping searches.

---

## 11. Open questions

**Device-side storage of saved flights — unanswered, and it is the same clause.**
A `SavedFlight` is a full provider DTO written to AsyncStorage and **never
deleted by age**. `isArchived` (6h past arrival) and `REFRESH_MAX_PAST_MS` (36h)
stop it being refreshed and shown, not stored; the only removals are the user
unsaving it and a legacy-key migration. A flight saved 60 days ahead therefore
holds provider data on the device for 60 days before it departs, and
indefinitely after.

Whether that breaches the seven-day limit has **not been put to AeroDataBox**.
Two readings:

- It is caching, in which case every saved flight older than seven days is
  non-compliant and the fix is a device-side prune — which would delete users'
  own trips and their history, a significant product change.
- It is the user's own record of their own booking, delivered at their request,
  which is closer to how the terms treat data displayed to an end user.

The second reading is more likely right, but the first has an expensive fix, so
get it in writing. Worth asking in the same thread: whether a departed flight's
DTO may be kept as trip history, and whether the seven days runs from fetch or
from the flight's date.

**Nothing else is open.** The three values that were unsettled when this
document was first written — the detour-ratio threshold (§4), the codeshare
tie-break (§7), and whether a same-carrier itinerary carries a caveat (§8) —
were decided on 2026-09-19 and are recorded above as decisions rather than
proposals. The only wording still to settle is the two caveat strings, which
Stage 3 fits to the row.
