# Terminal: complete handover

Written 24 September 2026, late evening IST, at the end of the long build chat (9 to 24 September). Verified by Claude Code in the first hour of 25 September IST against the repo (commit 1fb4d75), the Cloud Run service, the bucket and the logs, read-only. Corrections are applied throughout.

Who this is for: the next Claude chat in the "Flight tracker" Project, Claude Code on the new Mac, and Jay.

How to read it:
- Everything stated here was checked against the code, git history or the server on 25 September unless it is marked **[UNCONFIRMED: reason]**.
- File references are `path:line` at commit 1fb4d75. Line numbers drift; search for the named constant if a line has moved.
- Folders: the server is in `server/`, the React Native app in `android/`, the website in `website/`, docs in `docs/`. A bare server file such as `poller.py:216` means `server/poller.py`; app paths (`lib/`, `app/`, `components/`) are under `android/`; site files (`index.html`, `privacy.html`, `assets/`) are under `website/`. The dining and terminal data pipelines stay in the root `tools/`.
- Blocks marked private (between the two private comment markers) hold personal, account, device and money details. They live in the Project copy only and are never committed: the GitHub repo is public (confirmed). In the repo copy each block is replaced by one placeholder line.
- Where this doc and the code disagree, the code wins and the doc gets corrected. The exceptions are the open decisions in §2.4, where the code breaks one of Jay's rules and Jay decides which one changes.
- The old Project doc CONTEXT.md (8 September; archived in the repo as `docs/archive/CONTEXT.md`) is out of date in many places. This doc replaces it.
- The task list with steps and done-when checks is `docs/TASKS.md`.
- The Project copy also carries the Swift plan (a copy of `docs/SWIFT-REBUILD.md`) and the data investigation prompt as §19 and §20; the repo copy leaves them out.

---

## Direction from 25 September 2026
- The iPhone app is being rebuilt natively in Swift (SwiftUI, iOS 26 minimum), in a new `apple/` folder.
- The React Native app in `android/` is frozen, as the base for a future Android app. Sections below that describe it as the current iPhone app carry a note saying it is being replaced.
- The server in `server/` stays as it is; the Swift app uses the same endpoints.
- The full plan is in `docs/SWIFT-REBUILD.md`.

---

## 0. Snapshot: where everything stands

- **Live server:** Cloud Run revision `flight-tracker-00114-jev` serves 100% of traffic (tag `intent-eval`), with the diagnostic settings on. It runs the poller and every notification. Its uploaded source matches commit `76bc85c` exactly (all 189 files, compared file by file): the `/watched` endpoint, the faster tiers, the diagnostics and the `/intent` search server. It does **not** have connection search, the new notification wording, push expiry and collapse IDs, the landing summary, the GATE tier or the belt hold.
- **Built but not live:** revision `flight-tracker-00122-nay`, tag `landing`, 0% traffic. Its uploaded source is byte-identical to commit `1fb4d75` (all 245 files), so it carries every server commit: the final notification wording (route titles, one-line bodies), connection search with the budget gate, push expiry and collapse IDs, the landing summary push, 2-minute checks from 4 hours before departure (the new GATE tier) and "never send a belt before landing".
- **Traffic rule:** no traffic move until the beta trip is over; the live poller serves the beta tester's notifications. Jay approves the move; nobody moves traffic on their own. The move and the diagnostics clean-up happen in one step (task T3).
(Private details are kept in the Project copy, not in this repo.)
- **App:** TestFlight build 12 is the newest shipped build. Build 13 has not been made; Jay will make it on the Mac. Everything app-side since build 12 (departure delay count, landed early or late, timezone labels, the new search, connection search UI, alternatives drawer, disrupted-card redesign, the belt refresh fix and more) exists only in the repo and the dev client. Note: this describes the React Native app, which is being replaced by the Swift app (`docs/SWIFT-REBUILD.md`).
- **Repo:** branch `native-ios-tabs` at `1fb4d75`, in sync with GitHub. Working tree clean except the untracked `send_gmail_tests.py`. The default branch is `master` (there is no `main`).
- **Website:** new design committed (`f706569`), not deployed. The live site still serves the old design (live hero "One app for the whole flight.").
- **Mac:** arrives 25 September. Plan through Sunday 28 September: set up, app icon, UI overhaul, screenshots.
- **Launch target:** App Store submission around late October with a frozen v1 scope. Jay's older roadmap: booking in November, Android December or January.

### Next 72 hours, in order
1. The beta tester's last leg lands. Ask whether the test push arrived: its Expo receipt has expired, so asking is the only way to know (T1).
2. Confirm which install is on which phone before any test push (T2).
3. After the traffic time: move traffic and clear the diagnostics in the same step (T3).
4. Mac setup (§15, T6).
5. Review the diagnostic records for the three beta legs while they still hold provider values (T5; values are stripped six days after each event).
6. Pay for Google Workspace before its trial ends (T4).
(Private details are kept in the Project copy, not in this repo.)

---

## 1. How to work with Jay (read this before anything else)

### 1.1 Project instructions (verbatim, always in force)
These are addressed to the chat assistant in the Project. Claude Code follows its own prompt from Jay, which always says whether it may write.
- ALWAYS read the actual files before proposing changes. Never assume, guess, or hallucinate code that might exist.
- NEVER write, edit, or create files yourself, even if you have file access. All code changes go through Claude Code in VS Code. Your job is to think through the design with me, then hand me a prompt to paste into Claude Code, and always instruct it to show the diff and wait for approval before applying.
- Do exactly what I ask: no extra features, no unrequested refactors. If a change requires touching unrelated existing code, flag it rather than doing it silently.
- If you're unsure or my request is ambiguous, ask me before proceeding.
- Explain what changes do in plain language, not just code.
- Be honest about tradeoffs and tell me when something is a bad idea. Don't just agree with me.
- Design system is strict: #050505 background, #4ade80 green accent, minimal. Governing principle: terminal-flavored, not terminal-literal. Monospace and green for commands, codes and data; clean sans-serif for body text; real UI for spatial things. When the aesthetic fights legibility, legibility wins.
- When you explain things to me, use plain language with no code blocks. Code only ever appears inside a ready-to-paste Claude Code prompt, unless I explicitly ask to see code.
- Prefer one copy-paste Claude Code prompt that covers the whole task (apply, deploy, test, report) so I never have to hunt through files or run terminal commands myself.
- At the end of each task, give a plain-English summary for my log: simple bullets, no technical terms, no code, no file names, plain verbs like "Added", "Fixed", "Skipped".

### 1.2 Jay's personal preferences (from his settings)
- Match answer length to the answer's size. Bullets by default; prose only when an idea needs connective tissue. Plain English. No preamble, no restating the question, no closing recap. No em dashes.
- Don't narrate routine work. Tell him what changed and what it means.
- If there's a better approach, say it in one or two lines, then do it his way unless he bites.
- If something will break later, say so now. Push back when he's wrong; don't soften it into a question.
- Half-formed ideas are invitations to think, not specs. Ask what he's going for.
- Notice patterns across the codebase and mention them when they matter.
- If genuinely unsure between two designs, show both in a few lines each.
- Never dump full file contents into chat; show changed lines. Don't re-explain. Don't apologise or self-flagellate; say what broke and what's next.
- If a command fails the same way twice, stop and tell him.
- Skip builds, installs and dev server runs unless the change needs verifying. Don't create files he didn't ask for.
- Read a file before editing it. Never invent an API, prop, config key or path. Multi-file changes: short plan first, then wait. Flag risky or irreversible changes first. Don't touch formatting, imports or unrelated code. Refer to code by exact path and line. If he says stop, stop.
- "Brief" or "less words" means fewer words with the same content.

### 1.3 Lessons from this chat (mistakes not to repeat)
- **State costs before recommending anything.** Monthly, yearly, one-off and hidden costs (security reviews, verification fees, per-user fees). Two real failures: recommending Zoho Mail's free plan without checking (no IMAP on free, and paid plans were annual only), and not mentioning Google's CASA security assessment, needed to verify the restricted Gmail scope. Budget is tight and self-funded: prefer free, and say the price up front.
(Private details are kept in the Project copy, not in this repo.)
- **Search before stating a product, price or capability fact.** He said "go and search first" more than once. Never call something impossible without checking alternatives (another provider, a native API, a different endpoint).
- **Implement approved wording exactly.** When Jay approves copy, spacing or sizes, the Claude Code prompt must contain the exact strings and numbers. The layover warning took four rounds because prompts paraphrased him; he wanted an explanation, not a time.
- **Nothing gets committed or deployed before Jay reviews it when he asked to review.** Every prompt says: read first, show the diff, wait for approval.
- **Don't claim something works without evidence.** "Auto refresh" was declared done and then failed on the beta trip (see §9).
- **Check the source he names.** When he says "look at Flightradar24, not my server", check FR24.
- **Test pushes go only to Jay's own device**, never the beta tester's, unless he explicitly approves one. Confirm which install is Jay's first (T2).
- **Say whether a change needs a new build or reaches the phone through the dev server.** JavaScript-only changes reach the dev client through Metro; native changes need an EAS build. Don't burn builds on JS changes.
- **Don't propose limits that stop real users** (he rejected a per-device daily cap on connection searches: "we cant stop people like this").
- He works a day job; testing happens in the evenings; he won't open the laptop at night.
- He wants decisions laid out and makes them himself. He's the owner; don't override his calls with your own judgment, but do tell him when you think he's wrong.

### 1.4 Rules every Claude Code prompt must carry
- Read the relevant files first; show the diff; wait for approval before applying.
- Run all eleven server test suites before any server commit.
- For the app: `tsc` clean; eslint counts compared against the files' previous counts (several files already have lint errors, so "no new problems" is the bar); run the node test tools in `android/tools/` that apply.
- Deploy server changes only to a no-traffic tag, from a clean git worktree of the commit (a deploy from the main working tree uploads untracked files, see §10). Never move traffic. Never deploy without Jay.
- Settings changes use `--update-env-vars` and `--remove-env-vars`, never `--set-env-vars`.
- Never print secret values. When listing Cloud Run settings, print names only (for example `--format="value(spec.containers[0].env[].name)"`). Never print push tokens from `watches.json`.
- Test pushes to Jay's device only.
- Report in plain language; say what's committed, what's deployed, what isn't.

---

## 2. The product

### 2.1 What Terminal is
An iPhone app for everything about a flight. Jay's stated positioning: one app for booking (later), tracking, disruption recovery, airport intelligence (gates, food by security side, lounges, card benefits) and layover guidance; "if you have Terminal, you need no other travel app". Tracking is one feature, not the identity; don't frame it as a Flighty clone (the website must not look like a Flighty clone either), though Flighty is the quality bar he compares against.

Three differences from the category:
1. It asks the aircraft, not the airline: a landing is confirmed by Flightradar24's position data, not an airline status field.
2. It knows the airport: which side of security each place to eat is on, terminal schematics, layover time budget.
3. When a flight is cancelled it tells you what to do next (the next flights on the route, already found) instead of telling you to contact the airline. The long-term "main thing": help people get what they're owed after a disruption (refunds, compensation, rebooking entitlements) and keep helping after the trip is over.

### 2.2 Product rules (hard; they came from real incidents or Jay's direct decisions)
1. **Never tell the user to contact or check with the airline** (or "whoever holds your booking"). A disruption names the next flights instead. Confirmed: no user-facing string in the app or server contains "check with", "contact the airline", "contact your airline" or "whoever holds"; the only hits are comments and tests.
2. **No false, estimated-as-fact or ambiguous data.** Rejected on this basis: a boarding or gate-close countdown (no provider has boarding or gate-close times, and Jay refuses to estimate). A value we weren't given isn't shown. Absence is never an assertion.
3. **Flightradar24 is the only authority for "landed".** AeroDataBox once reported a landing for a flight still at its gate.
4. A departure "actual" counts only once it's in the past and has survived two polls (AeroDataBox revised an "actual" by 53 minutes once). Enforced for the "took off" push (`notify.py:566-573`). The poller's tier choice uses the actual time as soon as it is in the past, without the two-poll wait (`poller.py:440-442`).
5. Every FR24 landing query carries the departure instant (6E6188 on 7 September matched the previous day's rotation). NEAR asks FR24 only when a scheduled departure is stored (`poller.py:760-762`).
6. First sight of a flight is never a change; estimate moves under 5 minutes are not changes (`poller.py:641`).
7. **Colour:** green = live or actionable, amber = late or at risk, red = cancelled (including a cancelled booking). Nothing else is coloured.
8. **No pull-to-refresh anywhere.** The app refreshes itself (§6.3). The code breaks this rule today: see open decision D1.
9. **Public surfaces (website, X posts, emails to providers):** don't name data providers (including AeroDataBox), OpenStreetMap, or Gmail/Google on the website home page or in posts; show no Indian data (use JFK, LHR and similar); when writing to one provider, don't mention the others. Confirmed for the committed home page.
10. **Don't keep provider data on the device beyond need.** Alternatives are fetched when the drawer opens and never cached on the device (confirmed: `components/AlternativesDrawer.tsx:259-270`, state only).
11. **Spectators count.** People meeting a flight see it until it lands; flights that can no longer be caught stay visible and savable.
12. **Search: the model never picks airports.** The model returns names; the device resolves them against its own dataset.
13. **Watched vs owned.** Bookmark = watchlist (you're following it). Owned = My Flights (you're on it; it joins a trip). Home's watchlist shows only non-owned flights (`app/(tabs)/index.tsx:1607`); owned flights live in My Flights.
14. **Diversion is an in-flight event only.** Pre-departure test scenarios for diversion were removed.
15. **Push wording** leads with the route (title) and says what changed in one line (§6.1).

### 2.3 Design system and visual decisions
- Design rule: background #050505; accent #4ade80 for live and actionable only. The code's page background is `#0a0a0a` (`lib/cards.ts:198`); #050505 appears only in stale comments. See open decision D2. The accent is `#4ade80` (`lib/cards.ts:262`).
- JetBrains Mono for machine data (codes, times, flight numbers); Inter (sans) for human language. "Terminal as voice, not wallpaper."
- Contrast tokens (confirmed): DIM alpha 0.52 (`lib/cards.ts:236`), DIM_LARGE 0.4 for text 18pt and up (`lib/cards.ts:256`), SHEET_GRABBER_INK 0.45 (`components/DetentSheet.tsx:98`). A second contrast pass (0.55/0.6 tiers) is on the list.
- `borderCurve: 'continuous'` (Apple's G2 corners) on 48 code sites (confirmed); 18 capsules excluded.
- CARD_RADIUS 20 (`lib/cards.ts:134`); GLASS_RADIUS 24 (`lib/cards.ts:352`) and SHEET_RADIUS 24 (`lib/glass.tsx:108`); toasts became pills.
- Disrupted surfaces: opaque rgb(41,23,23) for cancelled, rgb(41,34,13) for diverted (DISRUPT_SURFACE, `components/FlightCard.tsx:366-369`).
- My Flights: the open trip card is borderless (`tripVariant`, `components/FlightCard.tsx:4301`); collapsed leg rows still draw a 1px hairline (`app/(tabs)/flights.tsx:1648`). Jay liked the clean look and wants all cards borderless. Dates grey and smaller.
- Clocks are 24-hour with the airport's zone label ("11:45 CEST"). When the phone's zone differs, the phone's time follows in a smaller size ("· 02:45 your time"), with the weekday only when the date differs.
- The native look Jay wants everywhere: the Profile sheet (a SwiftUI formSheet via @expo/ui). Drawers should feel like Apple's (Maps-style), resting at about a quarter or fifth of the screen.
- Jay's requirement for dark surfaces: at high brightness, blacks look like the void; at low brightness, nothing looks washed out or grey. Idea for the Mac: a brightness-aware palette using the screen brightness (needs a small native module).

### 2.4 Open decisions: where the code breaks a rule (Jay decides)
Recorded as open, not settled and not fixed. Each needs Jay to say which side changes.
- **D1. Pull-to-refresh.** Rule 8 says none anywhere, and §13 lists it as tried and rejected. The code has pull-to-refresh on Home (`app/(tabs)/index.tsx:1959-1960`) and My Flights (`app/(tabs)/flights.tsx:3342-3343`).
- **D2. Page background.** The design rule says #050505; the code uses `#0a0a0a` (`lib/cards.ts:198`).
- **D3. Notification permission on save.** Saving a flight asks for notification permission: save turns reminders on, which asks (`lib/saved.tsx:2176`, `lib/reminders.ts:69`), and registering the watch can ask too (`lib/watch.ts:186`), so two prompts can fire at once. The earlier decision was to ask only when setting a reminder.
- **D4. Layover warning after the first leg lands.** The handover said a landed first leg must not keep showing a connection warning. The code deliberately keeps it until the next leg is no longer scheduled, because the moment of landing is when it matters most (`app/(tabs)/flights.tsx:1079-1088`).
- **D5. Zone on the disrupted card's scheduled departure.** Jay had the zone removed from "SCHEDULED DEPARTURE 14:35". The zone-label work put it back ("THE ZONE NOW, LIKE EVERY OTHER CLOCK", `components/FlightCard.tsx:5244-5257`).
- **D6. Sort after a cancellation tap.** The server's deep link asks for the route list sorted earliest (`notify.py` deep_link; `app/_layout.tsx:176`), but the search screen ignores it and uses its Fastest default (`app/(tabs)/search/index.tsx:1420-1423`).

---

## 3. Architecture

### 3.1 Stack
- **App:** React Native 0.86.3, Expo SDK 57 (expo 57.0.19), React 19.2.3, Reanimated 4.5.1, expo-router 57.0.18 with NativeTabs (iOS 26 tab bar), react-native-screens 4.26.2, @expo/ui 57.0.15 (SwiftUI; used for the Profile formSheet), MapLibre GL JS 5.24.0 inside a WebView (GlobeMap, `components/GlobeMap.tsx:422`). No custom native code yet; native projects are generated in the cloud by EAS. iOS only; iOS 26 minimum deployment target (`app.json`, expo-build-properties `deploymentTarget "26.0"`), which blocks older iPhones permanently. Note: this describes the React Native app, which is being replaced by the Swift app (`docs/SWIFT-REBUILD.md`).
- **Server:** Python 3.12 (Dockerfile `FROM python:3.12-slim`) with FastAPI on Google Cloud Run, service `flight-tracker`, project `flight-tracker-496006`, region `asia-south1`, scaling 0 to 20 instances (maxScale 20), no min instances (cold starts happen). Deployed from source (Cloud Build), from the `server/` folder. Deploy notes in `server/DEPLOY.md` (partly stale, see T16).
- **State:** no database. Everything is JSON in Cloud Storage bucket `gs://flight-tracker-496006-alerts`, writes guarded by generation preconditions (several instances can poll at once).
- **Schedulers (Cloud Scheduler, asia-south1):** `flight-tracker-poll` (`*/2 * * * *`, UTC, POST `/poll`) and `flight-tracker-dispatch` (`* * * * *`, UTC, POST `/dispatch`), both ENABLED, each with its own secret header. They call the live service URL, never a tag, so tagged revisions never poll.
- **Push:** Expo push service to APNs.
- **Website:** static site in `website/`, hosted on Vercel, deployed by CLI.
- **AI:** Gemini for search intent, email extraction and the retiring chat. The provider is chosen by `LLM_PROVIDER` (code default "gemini"; "vertex" also supported; `llm.py:9-12, 56`). The setting is present on the live revision. [UNCONFIRMED: its value was not read, by the names-only rule.]

### 3.2 URLs
- Live: https://flight-tracker-970706733452.asia-south1.run.app (also https://flight-tracker-z2b3mixjea-el.a.run.app).
- Tag URLs: `https://<tag>---flight-tracker-z2b3mixjea-el.a.run.app` (for example `landing---...`).
- Website: https://www.terminalaero.com (legal links use www). Old Vercel URL: terminal-website-topaz.vercel.app (serves the same old page).

### 3.3 Bucket layout
| Path | What | Lifetime |
|---|---|---|
| `watches.json` | every watch row: device id, flight number, date, push token, owned or meeting, platform, created/updated times | live |
| `state/<NUM>/<DATE>.json` | per-flight poll state: last provider record, last landing answer, poll times, change ledger, notification state and outbox, delivery slots, alternatives | deleted 26 h after DONE (`poller.py:240`); 5-day sweep (`poller.py:257`); orphans (no watch) deleted after 26 h idle (`poller.py:1152-1153`) |
| `diag/<NUM>/<DATE>.json` | diagnostic record for flights in DIAG_FLIGHTS | provider values stripped 6 days after each event, whole record deleted 30 days after it was created (`diag.py:63-64`) |
| `routelists/` | AeroDataBox route lists for connection search | cached 6 days (`connections.py:70`); bucket lifecycle rule deletes at 6 days (confirmed on the bucket) |
| `boards/` | shared departure-board cache | code keeps 30 min (rolling) or 12 h (dated); bucket lifecycle rule deletes at 1 day (confirmed on the bucket) |
| `deliveries/` | records of the `/alerts` webhook deliveries | kept [UNCONFIRMED: no sweep found] |
| `sessions/`, `users/` | sign-in objects: one per Google account and one per live session (Google's numeric id, encrypted tokens, granted scopes; no name or email kept) | live |
| `runtime/` | landing breaker, landings cache, quota figure | live |

### 3.4 Endpoints (confirmed against `api.py:123-1824`)
Public: `/flight/{number}` (card data; `fresh=1` bypasses the cache and costs 2 units), `/route/{origin}/{destination}` (departure board filtered to destination), `/landing/{number}`, `/quota` (no provider call), `/intent` (the new search), `/connections/{origin}/{destination}` (`stream=1` NDJSON, `auto=1` for the automatic start), and the old `/parse` and `/chat` (kept until everyone is past build 12).
Session (bearer token): `/auth/google`, `/auth/signout` (revokes at Google), `/gmail/flights`; `/chat` accepts a session.
Secret-gated (a wrong secret returns 404, not 403, so probers learn nothing): `/watch`, `/unwatch`, `/watched` and `/alternatives` (X-Watch-Secret plus device_id), `/poll` (poll secret), `/dispatch` (dispatch secret), three `/alerts` webhook routes (secret in path: POST `/alerts/{secret}` and two GET deliveries routes).

### 3.5 Data providers
**AeroDataBox, direct plan** (moved off RapidAPI in September): Starter, 40,000 units a month, a limit of 5 requests a second (the code enforces 4, `mcp_server.py:423-443`), billing day the 14th (`pollstate.py:598`, confirmed). Costs: flight lookup 2 units, dated board 4 (a local day is two 12-hour requests), rolling board 2, route list 6 units flat. Base URL api.aerodatabox.com, header X-Api-Key, key in Secret Manager as `aerodatabox-api-key`. `AERODATABOX_GATEWAY` is not set on any revision; the code defaults to direct (`mcp_server.py:44`), and the live `/quota` reports gateway "direct". RapidAPI key removed from the server; the 401/403-only fallback path still exists in code (`mcp_server.py:68-72, 398-401`) but has no key to use, so treat it as dead. No quota endpoint; units remaining are read from response headers, and the code tries five header names because the direct gateway's name is not documented (`mcp_server.py:93-111`). Weakness: loses arrivals at Indian airports; says "landed" wrongly; bogus +00:00 offsets on local wall-clock times (parse with the sibling IANA zone). No boarding or gate-close time.
(Private details are kept in the Project copy, not in this repo.)

**Flightradar24 API**: landings (authoritative), takeoff time, diversion airport. Endpoint in use: flight-summary light. Billing per returned record (1 credit live, 2 for historic under 30 days; an empty answer still costs 1). Licence: 30-day storage limit. `dest_icao_actual` is always filled (equals the scheduled destination on a normal flight); the server compares the leg against itself and translates ICAO to IATA to detect a diversion airport. Measured coverage 7 September: 94.6% (106 of 112 finished flights); almost all misses were arrivals into Doha (accepted, not worked around). Token is a plain setting `FR24_API_TOKEN` (confirmed plain; rotation planned on the Mac). Unused endpoints worth measuring (Stage 2): flight events (gate_departure, takeoff) and live positions (about 6 credits a poll).
(Private details are kept in the Project copy, not in this repo.)

**Gemini:** search intent (`/intent`), email extraction, and the retiring chat. Key in Secret Manager as `gemini-api-key`.

**Google OAuth and Gmail API:** sign-in and read-only mail. The consent screen is "in production" but unverified: 100-user cap (4 used), and users see the unverified-app warning. Verifying the restricted Gmail scope needs a paid CASA assessment, which is why the plan is to replace Gmail reading with a forwarding address (§16).

**Expo push / APNs:** Apple stores only one notification per app for a phone that's offline (Apple engineer, Feb 2025), chosen non-deterministically. That shaped the expiry and collapse design (§6.1).

### 3.6 Licence rules (AeroDataBox and FR24)
- AeroDataBox said route data is "Contents": 7-day cache ceiling, and reshaping it doesn't change that ("Derived Work" needs all three of their tests). So route lists are cached 6 days (contract note in `connections.py:63-69`) and bucket lifecycle rules enforce it even if code fails (confirmed on the bucket: `routelists/` 6 days, `boards/` 1 day).
- The diagnostic records strip provider values at 6 days; the remaining "what we did and when" skeleton is treated as our own process record, though AeroDataBox hasn't been asked about that reading. The strip and delete sweep runs on every poll pass whether or not DIAG_FLIGHTS is set (`poller.py:1159-1163`); it is skipped only if the bucket or the watch store can't be read, so it keeps working as long as the poll scheduler runs.
- **Open question (connection-search spec §11):** saved flights on the device live beyond 7 days. Not yet put to AeroDataBox. A second question (aircraft type for flight history) was never sent: Jay declined to email them again and said not to mention other providers when writing to them.
- FR24: 30-day storage limit.

### 3.7 Repository map (branch native-ios-tabs)
Server (`server/`): `mcp_server.py` (provider calls; `_adb_get` is the single AeroDataBox request helper; `_build_route_row` emits origin_iata, revised/runway/live fields and the `departed` flag with a pre-departure-status veto; country and the arrival-belt hold in `_build_movement`; bucket board cache; rate gate), `poller.py`, `pollstate.py`, `notify.py`, `dispatch.py`, `diag.py`, `store.py`, `api.py`, `fr24.py`, `connections.py`, `llm.py`, `auth.py`, `gcs.py`, `airport_geo.py` (generated from OurAirports, public domain), `airport_icao.py` (3,986 ICAO/IATA pairs), `gmail_flights.py`, `Dockerfile`, `.dockerignore`, `.gcloudignore`, DEPLOY.md; `tools/` holds the intent eval, the Gmail test emails the server reads (`tools/gmail_fixtures/`) and the airport data generators (`tools/icao/`).
Server tests (11 suites, all passing on 25 September): test_notify (153), test_poller (169), test_dispatch (87), test_fr24 (53 checks, prints no total), test_auth (60), test_gmail_flights (137), test_alternatives (21), test_watched (24), test_diag (27), test_connections (79), test_intent (38); plus `server/tools/eval_intent.py` (two 40-line eval sets).
App (`android/`, frozen as the base for a future Android app): `lib/saved.tsx` (store; connectionRisk, departurePhase, watchLive, the /watched reader), `lib/storage.ts` (SCHEMA_VERSION 15, `lib/storage.ts:7`), `lib/watched.ts`, `lib/watch.ts`, `lib/checked.ts`, `lib/departure.ts`, `lib/arrival.ts`, `lib/landing.ts`, `lib/reminders.ts`, `lib/alternatives.ts`, `lib/connections.ts`, `lib/connectionStream.ts`, `lib/routeResults.tsx`, `lib/airports.ts`, `lib/zoneAbbr.ts`, `lib/time.ts` (yourTime, clock24), `lib/flightstatus.tsx` (zonedClock), `lib/cards.ts` (tokens), `lib/gmailPull.tsx`, `lib/devFixtures.ts`, `components/DetentSheet.tsx`, `AlternativesDrawer.tsx`, `ResultsSheet.tsx`, `RouteRow.tsx`, `FlightCard.tsx` (about 6,000 lines), `GlobeMap.tsx`, `app/(tabs)/flights.tsx`, `index.tsx` (Home), `deck.tsx`, `search/index.tsx`, `app/profile.tsx`, `app/_layout.tsx`.
App node tests (`android/tools/`, all passing on 25 September): test_airports.mjs (127), test_departure.mjs (40), test_arrival.mjs (17), test_pending_rules.mjs (25), test_connections_client.mjs (20), test_map_loader.mjs (25); probes probe_airports.mjs, probe_yourtime.mjs; alias generator aliases.mjs and add_aliases.mjs.
Docs: `docs/connection-search.md` (settled spec, §11 open question, §12 decisions while building Stage 2; partly stale, see T16), `docs/HANDOVER.md` (this doc, public copy), `docs/TASKS.md`, `docs/archive/CONTEXT.md` (out of date, kept as history). The React Native app's native-iOS conversion spec is `android/SPEC.md`.
Data pipelines (root `tools/`): `tools/dining/` and `tools/terminals/` build `android/lib/dining.ts` and `android/lib/terminals.ts`; `tools/indoor/` is a Mapbox probe page.
Website (`website/`): index.html, privacy.html, terms.html, support.html, 404.html, vercel.json (cleanUrls), assets/ (page.css for the home page, site.css for the other pages, board.js, dining.js, og.png, fonts, phone placeholders), tools/ (phones.py puts screenshots into Apple's bezel, pictograms.py, dining_sample.py, icons.py, og.html, og.css, bezel/), .vercelignore (excludes tools). The bezel image is kept out of git (`tools/bezel/.gitignore`, confirmed untracked).

### 3.8 Generated datasets (ship in the app)
- Airports: 1,223 with city, country, IANA zone; India bias deliberate. 880 aliases on 324 airports plus 230 aliases on 38 city groups, across 24 scripts (§6.6).
- Dining: 753 outlets at 8 airports (BOM 149, JFK 139, EWR 118, FRA 83, HKG 76, LGA 72, ARN 65, LHR 51), each tagged before/after security (explicit or inferred), opening hours kept verbatim. The website counts 604 places at seven airports because Mumbai is excluded from public surfaces.
- Terminals: 24 terminals at 10 airports (ARN, BLR, BOM, DEL, EWR, FRA, HKG, JFK, LGA, LHR) from OpenStreetMap (ODbL: attribution required wherever drawn), with a straight-line honesty score for gate order.
- ICAO/IATA pairs: 3,986, in the server (`airport_icao.py`), not the app.

---

## 4. Server state in detail

### 4.1 Revisions and tags (from `gcloud run revisions list` and the traffic block, 25 September)
"Built from" was proven by comparing each revision's uploaded source bundle with git, file by file.

| Revision | Tag | Traffic | Built from |
|---|---|---|---|
| 00123-piq | restructure | 0 | `server/` at `c022f81` (50 files, byte-identical): the same server code as 00122, relocated to `server/`; the service template |
| 00122-nay | landing | 0 | exactly `1fb4d75` (245 files): everything |
| 00121-zid | none | 0 | exactly `4160c21` (superseded) |
| 00120-rih | none | 0 | `ca1932d` (superseded) |
| 00119-wuy | wording | 0 | `a5cb8eb` plus the first short wording, then uncommitted |
| 00118-tar | connections | 0 | `a5cb8eb` plus connection search Stage 3, then uncommitted |
| 00114-jev | intent-eval | **100%** | exactly `76bc85c` (189 files) |
| 00111-juf, 00111-42n | none | 0 | earlier search work (two revisions share the number) |
| 00107-krx | none | 0 | near `9b3de83` plus uncommitted files; its upload included `send_gmail_tests.py` and `.claude/settings.local.json` (see T8) |

**The service template is now 00123's image.** Revision 00123 was deployed from `server/` after the repo restructure; its code is the same as 00122's, relocated. Any settings change on the service creates a new revision running 00123's code, so the traffic move (T3) builds from it. Traffic is pinned to 00114 by name, so such a revision gets 0% and 00114 keeps running unchanged.

### 4.2 Settings (names only; never print values)
The same 18 names on 00114 and 00122.
- From Secret Manager: `AERODATABOX_API_KEY` (secret `aerodatabox-api-key`), `GEMINI_API_KEY` (`gemini-api-key`), `TOKEN_KEY` (`token-key`).
- Plain values: `ALERTS_BUCKET`, `ALERT_WEBHOOK_SECRET`, `ALERT_READ_SECRET`, `LLM_PROVIDER`, `VERTEX_PROJECT_ID`, `VERTEX_REGION`, `CHAT_MODEL`, `PARSE_MODEL`, `WATCH_SECRET`, `FR24_API_TOKEN`, `POLL_SECRET`, `GOOGLE_IOS_CLIENT_ID`, `DISPATCH_SECRET`, `DIAG_FLIGHTS` (the three beta legs), `DIAG_DEVICE` (the beta tester's install id).
- Not set anywhere (code defaults apply): `AERODATABOX_GATEWAY` (direct), `RAPIDAPI_KEY` (removed), `EXPO_ACCESS_TOKEN`, `POLL_MAX_ADB` (40), `POLL_MAX_FR24` (60).

(Private details are kept in the Project copy, not in this repo.)

Cloud Run source deploys keep existing setting values.

### 4.3 Poller
Reads watches.json, gives each flight a tier from stored state (no call), fetches only what's due, diffs, records changes, decides notifications, writes the outbox; dispatch sends every minute.

| Tier | Live now (00114) | After the move (00122) |
|---|---|---|
| DISTANT (more than 48 h out) | every 12 h | same |
| FAR (48 h to 6 h) | every 6 h | same |
| DAY | 6 h to 90 min, every 10 min | 6 h to 4 h, every 10 min |
| GATE | does not exist | **4 h to 90 min, every 2 min, AeroDataBox only (no FR24)** |
| NEAR | last 90 min, every 2 min, plus FR24 | same |
| AIRBORNE | every 5 min, plus FR24 | same |
| ARRIVAL (from 30 min before arrival) | every 2 min, plus FR24 | same |
| DONE | landed and at the gate, or 3 h past arrival with no gate time, or cancelled | same |

Sources: `poller.py:20-26, 91-143, 162-177, 221`. The GATE window is read from `notify.GATE_WINDOW`, so the push window and the check window can't drift apart.
- Consecutive misses double the interval up to 6 h (`poller.py:192`); one good answer resets. Per-run caps: 40 AeroDataBox calls and 60 FR24 calls (`poller.py:270-271`).
- Budget floor (40 units a day times the days to the reset, `pollstate.py:603-620`) gates only the AeroDataBox call, not the flight: below it, FR24 still runs and AIRBORNE and ARRIVAL still ask AeroDataBox (`poller.py:742`). GATE gives way below the floor like DAY and NEAR. NEAR asks FR24 only when a scheduled departure is stored.
- "Departed" has a third proof: an FR24 takeoff time in the past from a pending or landed answer, accepted only if no more than an hour before the scheduled departure (`poller.py:216, 465-471`; guards against an earlier rotation of the same number).
- Cost per ten-hour flight: AeroDataBox about 572 units after the move (210 originally, 452 measured after the tier speed-up; the GATE tier adds up to 120, `poller.py:134-138`). The GATE tier adds no FR24 credits (confirmed: GATE is not an FR24 tier). FR24 about 174 credits per flight [UNCONFIRMED: not re-measured]. A three-leg long trip is roughly 1,100 to 1,400 units [UNCONFIRMED: estimate]. The monthly 40,000 covers roughly 70 long-haul flights at 572 each.
- Stale undeliverable messages don't hold a flight open.
- Cancellation: tier DONE, but the next-flight search continues on later polls.

### 4.4 Diagnostics (on the live revision)
For the flights in DIAG_FLIGHTS and the device in DIAG_DEVICE only: every poll (time, tier, providers asked, errors, changed field names and values), every notification decided and every one decided against with its reason, every delivery stage (sent, delivered, not_delivered, send_failed, dropped, expired). Stored at `diag/<NUMBER>/<DATE>.json`. Polls that are not due aren't recorded (they return before the diagnostic write, `poller.py:770-772, 974`).

**Stopping them is part of the traffic move (T3).** Clearing DIAG_FLIGHTS on its own now creates a new zero-traffic revision from 00123's code (the service template) while 00114 keeps recording (§4.1). The licence clean-up does not depend on the setting: the strip and delete sweep runs on every poll pass regardless (§3.6).
(Private details are kept in the Project copy, not in this repo.)

### 4.5 Connection budget gate
Automatic connection searches (started because a route has no direct flight) run only while remaining units exceed 500 × days until the reset (for example 10,500 with 21 days left): `CONNECTIONS_RESERVE_PER_DAY = 500` (`pollstate.py:636-641`), `auto_allowed()` (`connections.py:292-307`; an unknown budget means no). Otherwise the sheet shows "Show connections" (`components/ResultsSheet.tsx:1192`), and a search the person asks for always runs. A 70% warning is logged once per process per billing period when 28,000 units are used (`pollstate.py:648-669`). The 500 figure was "one ten-hour flight" when that cost 452; it's now about 572, so the reserve should be revisited (Jay's call; the comment at `pollstate.py:629-630` still says 452).

---

## 5. Builds, TestFlight and the dev workflow
> Note: this describes the React Native app, which is being replaced by the Swift app (`docs/SWIFT-REBUILD.md`).

### 5.1 Workflow
- Dev client: `npx expo start --dev-client` from `android/` (add `--clear` if Metro misbehaves; OneDrive reparse tags broke Metro on Windows). Phone and computer must be on the same Wi-Fi. Force-quitting the dev client breaks the connection; reopen from the dev launcher. Port conflict: `npx kill-port 8081`.
- `android/.env.local` points dev builds at an old tag URL (EXPO_PUBLIC_API_BASE, honoured only in `__DEV__`, `lib/saved.tsx:117-118`). Don't copy it to the Mac; delete it on Windows.
- `android/.env` holds `EXPO_PUBLIC_WATCH_SECRET`. It is git-ignored and `eas.json` has no env block, so an EAS cloud build does not get it unless it is set in EAS; earlier TestFlight builds shipped an empty secret (`lib/watch.ts:266-270`). Build 13 must supply it (T9).
- EAS builds run from the `android/` folder (a command pasted with a label once failed). `eas.json` has development, preview and production profiles; production has `autoIncrement: true`; `appVersionSource` is `remote`, so EAS keeps the iOS build number and `app.json`'s `buildNumber "10"` is likely ignored. There is a production submit profile. [UNCONFIRMED: the exact command used for builds 11 and 12 is not recorded anywhere in the repo; production profile plus auto-submit is the likely route.] A build takes about 30+ minutes, then Apple processing; the tester updates in the TestFlight app. Apple's "ready" email may not arrive; check TestFlight directly.
- Notification taps in a dev build can open the dev launcher instead of the app when Metro isn't connected; that's the dev client, not the app.
- Dev and TestFlight builds share the bundle id today, so they can't coexist on one phone. Planned: a separate dev bundle id; `expo-dev-client` out of production dependencies (it is in `dependencies` today, `package.json:26`).
- App name on the home screen "Terminal"; App Store Connect app name "Terminal Flights"; version 1.0.0.
(Private details are kept in the Project copy, not in this repo.)

### 5.2 Build history
- Build 9, then 10 (Jay's phone via TestFlight), 11 (21 Sep 18:40), 12 (the beta tester's; user agent "Terminal/12"). Build 13 not made.
- Build 12 carries the /watched minute reader but also the fault that stops refreshing once a belt appears (§9).
- The Profile screen's "Dev only" rows are hidden behind `__DEV__` and have been since they were added (commit bd392b6; `app/profile.tsx:550, 585`; the Deck's "DEV ONLY · FORCE TERMINAL" too, `app/(tabs)/deck.tsx:748`). A TestFlight release build should not show them. [UNCONFIRMED: the chat believed the TestFlight builds show them; check on a TestFlight install.] The real release problem is that `lib/devFixtures.ts` still ships (T10).

### 5.3 What build 13 will carry (from the repo)
App-side belt fix; departure delay count; landed early or late; timezone labels and "your time"; new search with /intent; connection search UI and saving; alternatives drawer; disrupted card redesign; layover warning copy; catchability bands and "Active flights"; bookmark vs owned for connections; the dev menu's website screenshots. **Not built:** the header clock and greeting following the trip's city (T12) and "time to leave" for the first leg only (T13); both were planned and never started (no commits, no stash). Before building: the watch secret (T9), devFixtures (T10), the storage fault (T11). Plus whatever the Mac UI overhaul changes. After everyone is on 13, retire `/parse` and `/chat`.

(Private details are kept in the Project copy, not in this repo.)

---

## 6. Features as built (the detail that isn't obvious from the code)
> Note: this describes the React Native app, which is being replaced by the Swift app (`docs/SWIFT-REBUILD.md`). The server-side behaviour described here stays.

### 6.1 Notifications (final wording is on 00122, not live yet)
**Title:** route plus flight number, the same for the traveller and someone meeting the flight. City names if the whole title is 26 characters or fewer (`TITLE_MAX`, `notify.py:1063`; "Amsterdam → Mumbai · KL871" is exactly 26), otherwise airport codes at both ends ("SFO → LHR · BA286"), never one of each. A missing city means codes. No route known means the flight number alone.
**Body:** one short line, 24-hour clock with the airport's zone. Traveller: "Your flight's...", "Your bags...". Meeting: "The flight...", "The gate...", "The bags...". It names the old value wherever something changed (gate, terminal, belt, the airport a diverted flight landed at) except a time: "delayed 25 min" already says what moved. Messages queued before this wording read the same way: the values keep the record's 12-hour text and the renderer converts.

### 6.1a Definitive strings (rendered by `notify.py` at 1fb4d75 with sample values; `test_notify.py` asserts these forms)

| Kind | Traveller | Meeting the flight |
|---|---|---|
| Gate changed | Your flight's gate changed from E2 to E6 | The gate changed from E2 to E6 |
| Gate first given | Your flight's gate is E6 | The gate is E6 |
| Gate first given, with terminal | Your flight's gate is B32, in Terminal 5 | The gate is B32, in Terminal 5 |
| Gate, 4th change (the last gate message) | Your flight's gate changed again, from E6 to F4 | The gate changed again, from E6 to F4 |
| Departure terminal | Your flight now leaves from Terminal 3 instead of Terminal 2 | The flight now leaves from Terminal 3 instead of Terminal 2 |
| Delayed | Your flight is delayed 25 min, now leaves at 21:15 CEST | The flight is delayed 25 min, now leaves at 21:15 CEST |
| Delayed again | Your flight is delayed again, now leaves at 21:40 CEST | The flight is delayed again, now leaves at 21:40 CEST |
| Delay shorter | Your flight's delay is shorter, now leaves at 21:05 CEST | The flight's delay is shorter, now leaves at 21:05 CEST |
| Back on time | Your flight is back on time, now leaves at 20:50 CEST | The flight is back on time, now leaves at 20:50 CEST |
| Cancelled, next found | Your flight is cancelled, next is KL879 tomorrow at 14:25 CEST | The flight is cancelled, next is KL879 tomorrow at 14:25 CEST |
| Cancelled, next further out | Your flight is cancelled, next is KL871 on Sunday at 20:50 CEST | The flight is cancelled, next is KL871 on Sunday at 20:50 CEST |
| Cancelled, next has no number | Your flight is cancelled, the next flight leaves tomorrow at 14:25 CEST | The flight is cancelled, the next flight leaves tomorrow at 14:25 CEST |
| Cancelled, still searching | Your flight is cancelled, finding the next flight | The flight is cancelled, finding the next flight |
| Cancelled, none this week | Your flight is cancelled, no other flight this week | The flight is cancelled, no other flight this week |
| Search follow-up, found | Your flight was cancelled, next is KL879 tomorrow at 14:25 CEST | The flight was cancelled, next is KL879 tomorrow at 14:25 CEST |
| Search follow-up, none | Your flight was cancelled, no other flight this week | The flight was cancelled, no other flight this week |
| No longer cancelled | Your flight is no longer cancelled and leaves at 20:50 CEST | The flight is no longer cancelled and leaves at 20:50 CEST |
| Took off | Your flight took off and lands around 10:05 IST (or "Your flight took off") | The flight took off and lands around 10:05 IST (or "The flight took off") |
| Landing time moved | Your flight now lands around 10:40 IST | The flight now lands around 10:40 IST |
| Arrival terminal | Your flight now arrives at Terminal 2 instead of Terminal 1 | The flight now arrives at Terminal 2 instead of Terminal 1 |
| Landed, final stop | Your flight landed at 09:53 IST, 12 min early, bags on belt 4 | The flight landed at 09:53 IST, 12 min early, bags on belt 4 |
| Landed, on time | Your flight landed at 09:53 IST, on time | The flight landed at 09:53 IST, on time |
| Landed, with a next leg | Your flight landed at 07:32 BST, 9 min late, next is LX325 at 11:50 BST from gate A12 | The flight landed at 07:32 BST, 9 min late |
| Landed, next leg has no gate yet | ...next is LX325 at 11:50 BST from Terminal 2 | (as above) |
| Landed, connection threatened | ...from gate A12, connection at risk / connection won't hold | (as above) |
| Landed, next leg cancelled | Your flight landed at 07:32 BST, 9 min late, next flight LX325 is cancelled | (as above) |
| Landed elsewhere | Your flight landed at HYD instead of Mumbai (or "Your flight landed, but not in Mumbai") | The flight landed at HYD instead of Mumbai (or "The flight landed, but not in Mumbai") |
| Belt | Your bags are on belt 4 | The bags are on belt 4 |
| Belt moved | Your bags are now on belt 7 instead of belt 4 | The bags are now on belt 7 instead of belt 4 |
| Diverted | Your flight has been diverted from Mumbai, landing airport not known yet | The flight has been diverted from Mumbai, landing airport not known yet |
| Connection at risk | Your connection to LX325 in London is at risk | The connection to LX325 in London is at risk |
| Connection won't hold | Your connection to LX325 in London won't hold | The connection to LX325 in London won't hold |
| Anything unrecognised | Your flight was updated | The flight was updated |

**Rules (confirmed in `notify.py` and `dispatch.py`):**
- Gate messages only inside 4 h of departure (`GATE_WINDOW`), baseline taken when the window opens, value must hold two polls (`SETTLE_POLLS`); three gate messages, then one final "changed again" message, then silence (`GATE_CAP_COUNT = 3`).
- Delay: within 12 h, at least 15 min, at least 15 min of movement since the last, at least 30 min since the last delay message, settled over two polls. Back on time when the delay drops to 5 min or less (`notify.py:76-83`).
- One message per flight per 20 minutes (`FLIGHT_FLOOR`), except cancelled, no longer cancelled, landed, diverted, next flight, belt and connection (`notify.py:97-100`). Cancellation also skips the settle rule. It is deferred to 07:00 only if it would arrive between 22:00 and 07:00 at the departure airport and the flight is more than 24 h out (`notify.py:174-176`, `_quiet_deferral`).
- Next-flight search after a cancellation: up to 7 days ahead (`NEXT_MAX_DAYS`, was 60); a replacement must leave at least 90 minutes after **now**, the moment of the search (`NEXT_MIN_LEAD`, `notify.py:225, 967`), so a flight leaving before the cancelled one would have is offered if it can still be reached; keeps 8 rows (`NEXT_KEEP_ROWS`); records searched_at. Tapping a cancellation opens the route list (`app/_layout.tsx:164-176`); the server asks for earliest-first but the app shows its Fastest default (open decision D6).
- Landing summary: one push that says everything (landed time and early or late from touchdown; next leg's flight, time and gate or terminal; next leg cancelled; connection at risk, in which case the separate connection push isn't sent). Belt only on the last leg or an arrival into the US from abroad (`BAGS_RECLAIMED_ON_ENTRY`). Meeting someone: landed, figure, belt; no next leg.
- Expiry by kind (sent messages; 15 min floor, 24 h ceiling, 1 h when a message carries none, `dispatch.py:161-170`): gate, fourth gate change, terminal, delay, back on time and no longer cancelled until that flight's expected departure + 15 min; cancelled and next flight 24 h; connection messages until the onward departure; took off, landing time and arrival terminal until expected arrival + 15 min; landing summary until the next leg's departure, else 2 h after landing; belt 45 min; diverted 6 h (`notify.py:153-160, 768-793`).
- Separately, dispatch drops a message that was never sent once it has waited too long: gate 30 min, belt 45 min, delay, back on time, took off, landed and landing time 1 h, terminal, arrival terminal, cancelled, no longer cancelled, next flight, diverted and connection 2 h (`STALE_AFTER`, `dispatch.py:104-132`).
- Collapse IDs per flight for kinds where the newer message makes the older one wrong: gate (with the fourth-change message), departure time (delay and back on time), terminal, cancelled and no longer cancelled, connection, arrival time, arrival terminal, belt (`dispatch.py:184-196`). Not the landing summary, next flight, took off or diverted.
- Pushes carry the airport's zone only; the server doesn't know the reader's zone.
- A phone in airplane mode gets nothing until it reconnects, and then Apple delivers only one held notification per app, which is why the landing summary must be complete on its own.
- **Known bug:** "Took off" fires on the gate-out time: the push is decided from the departure actual time (`notify.py:384, 566-577`), which is the gate time (`mcp_server.py:660-661`), but says "took off". Fix planned in FR24 Stage 2.

**Device-scheduled reminders** (not from the server, `lib/reminders.ts`):
- Evening before, at 18:00 origin-local time: title "<flight number> tomorrow", body "Departs <origin code> at <time>. Terminal <t>. Scheduled time." (`lib/reminders.ts:179-185`).
- Time to leave, 3 h before a domestic departure or 4 h before an international one: title "<flight number>", a long dash, then "time to leave"; body "Head to <origin code>. Scheduled departure <time>. Terminal <t>." (`lib/reminders.ts:187-193`). The time reads like "11:45 CEST (02:45 your time)".
- There is **no first-leg-only rule**: every saved flight with reminders on gets its own pair (`lib/reminders.ts:221-233`, `lib/saved.tsx:2218-2223`). Jay's rule ("time to leave" only for the first leg of a trip; connecting legs get their own reminders) was planned and never started (T13). The wording still leads with the flight number, unlike the new push style (T14).

### 6.2 Push permission and registration
- Saving a flight writes it locally and registers a watch on the server.
- The saved-flight limit is `MAX_SAVED_FLIGHTS = 500`, commented "NOT A LIMIT TODAY" (`lib/storage.ts:8-25`); the Gmail pull is capped separately, and owning a flight by hand skips the cap. The only 20 is `MAX_MAP_ROUTES` (routes drawn on the map, `lib/storage.ts:1053`); four comments still say the watchlist cap is 20.
- Signing out deregisters this device's watches one at a time in the background (the single watches.json can't take parallel writes), skips flights also in the guest list, and resets the per-account backfill marker so the next sign-in re-registers (`app/profile.tsx:348-363`, `lib/watch.ts:452-530`).
- Fixtures are installed without registering, and `isDevFixture` filters them out of /watched, the landing sweep, the pull, the backfill and alternatives. But `registerWatch` has no guard of its own: undoing the unsave of a fixture, or disowning one, registers it with the server, and disowning clears the dev trip id so a screenshot fixture with a real number (BA177) stops being recognised as a fixture (T10).
- Push permission is asked when a flight is saved (open decision D3), and by the remind swipe and the Profile notifications toggle. The Gmail pull doesn't ask.

### 6.3 Automatic refresh (/watched)
- One batched request a minute (`WATCH_EVERY_MS`, `lib/saved.tsx:793`) while the app is in the foreground, for live flights only. Zero provider units: it returns the stored poller record, landing answer, and a corrected data age (the endpoint adds time since the poll, so old data never looks fresh). Returns owned and meeting flights the device watches; other pairs are silently omitted. Capped at 12 flights a request on both sides (`lib/watched.ts:51`, `api.py:1664`); the app sends the first 12 live flights in saved order, not by urgency.
- Live window (`watchLive`, `lib/saved.tsx:775-784`, repo only, build 13): from 6 h before departure. Before landing a belt is ignored, and without a known landing the window runs until 3 h after the expected arrival (`lib/landing.ts:74, 118-121`). After landing it stops when a belt appears or 45 min after the landing, whichever is first.
- The label reads "updated X ago" (Jay chose "updated", not "checked") and shows the later of the app's last fetch and the provider's data time (`lib/flightstatus.tsx:415-417`); rows show it only after a fetch while the app is open, and the card never shows it.
- A result is applied only if its data is newer (`lib/saved.tsx:1960`; there is no "different" test). A manual refresh asks the provider fresh (`fresh=1`, 2 units).
- Freshness ceiling is the poller tier, not the minute.
- Build 12 fault: a belt published early stops the refresh (§9). Fixed in the app for build 13 and on the server (belt never sent before landing, 00122).

### 6.4 Departure delay count (app, build 13; confirmed in `lib/departure.ts`)
- Past its scheduled time and still at the gate: status pill "DELAYED 12M" in amber, counting up every minute; the figure is the larger of minutes since scheduled time and the airline's estimate (`lib/departure.ts:143-147`). Shows on the departure clock, the collapsed leg chip, watchlist rows ("delayed 12m") and the trip folder colour.
- Needs data less than 30 min old (`COUNT_FRESH_MS`), otherwise nothing counts. Only a "scheduled" flight counts.
- Off the gate: count stops; "left the gate 19:58 IST · 18m late" (or "· on time"). Gate time trusted only when the provider tracks the departure live; 45 min after the gate time with no takeoff shows as in the air without a takeoff time (`TAXI_OUT_MAX_MS`).
- Off the ground: "took off 20:11 IST" from FR24's takeoff or the provider's runway time. An FR24 takeoff also moves a "scheduled" flight to in the air; a runway time does not. Times more than an hour before the schedule are not believed (`EARLY_SLACK_MS`, `lib/departure.ts:28-36, 84-89`).
- The Deck, the map plane and the progress arc wait for takeoff instead of switching at the scheduled time.
- Jay's decisions: leaving the gate is display only (decided, not a push); spending FR24 credits on a one-minute watch is decided after measuring the FR24 endpoints (Stage 2).
- Not covered yet [UNCONFIRMED: not re-checked]: Home and search cards still read "Actual Departure 19:58 · 18m late" without takeoff; collapsed legs show the count but not gate/takeoff lines; Home's collapsed summary hides status; Deck keeps showing the origin while taxiing.

### 6.5 Landing figure (app, build 13; confirmed in `lib/arrival.ts:51-61`)
"Landed 08:27 · 38m early" from FR24 touchdown, else the provider's runway time; "Arrived 08:34 · 31m early" when only a gate arrival exists. Shown on watchlist rows, archive rows, collapsed landed legs, the landed trip card (belt stays the main answer during the 45-min bag window, then LANDED becomes the headline), and Home/search cards. The airline's own gate-based figure would read 5 to 10 min less early.

### 6.6 Search (server half /intent is on the live 00114, confirmed; device half in build 13; build 12 still calls /parse and /chat)
- Free rungs first, no model call: flight number in any form; code pairs with any separator (`/ , . _` between codes); name pairs with a trust rule (both ends exact, or one end a unique one-edit typo but not both); a single place. Then one `/intent` Gemini call returning structured intent: search_route, lookup_flight, or prose. The model never picks airports; the device resolves names at rank 2 or better.
- Flight-number searches respect a typed date (a past bug saved an earlier day's instance of a flight when a later date was typed); past dates parse too.
(Private details are kept in the Project copy, not in this repo.)
- Question shapes answered in one line under the sort pill from the filtered rows, never from an uncatchable flight: next, first, last, fastest, arrival, count, airlines ("Next flight to Indore is IndiGo 6E5071 at 14:20 from Delhi"). The line carries zones and "your time". "Show me the fastest" is a request and only sets the sort.
- No origin given: uses the position pin already resolved; never prompts for location again; without a pin, asks for the origin by example. Notes under the pill: "From Bengaluru, assumed from your location", "Searching 26 Sep, the first day of this weekend".
- Resolver: 1,223 airports; diacritic folding; all scripts kept; typo tiers Latin-only; OSA edit-distance tiers; `isKnownPlace` from the haystack; 38 curated multi-airport city groups (`lib/airports.ts:1345-1631`), including Tokyo HND/NRT, New York JFK/EWR/LGA, London LHR/LGW/STN/LTN, Paris, Milan, Moscow, Washington, Buenos Aires, São Paulo, Shanghai, Seoul, Bangkok, Istanbul, Los Angeles, Bucharest, Chicago, Rome, Beijing, Osaka and more, plus single-airport entries such as Hong Kong and Singapore; 880 airport aliases plus 230 city-group aliases in 24 scripts (endonyms like München, Praha, 東京, Москва, दिल्ली); SAME_NAME table ordered by traffic for Barcelona, Brest, Portland, San Jose, San Salvador, Santiago and Valencia (`lib/airports.ts:2178-2186`); country hints from the model order options, never drop them; the picker shows the country when options span countries. Not in the dataset by Jay's decision: Hyderabad (Pakistan), Springfield; Kyiv has no scheduled service. Renamed airports point at current codes (Rajkot HSR, Yogyakarta YIA, Siem Reap SAI, Phnom Penh KTI, Dakar DSS; confirmed, old codes absent).
- Evals: 0 of 40 misread on the India set and on the world set (eight European languages, Arabic, Persian, Japanese, Chinese, Korean, Thai, Indonesian); 10 of 10 question shapes. [UNCONFIRMED: evals not re-run; they call the model.]
- Retired: the forced retry (it produced a confident wrong route for "what is the weather in delhi"); the two-press reading.
- Stripped strings (fillers removed) must resolve at rank 2; "delhi/indore" costs one model call, "del/idr" is free.

### 6.7 Route results sheet and catchability
- Results open in a custom bottom sheet (ResultsSheet on the shared DetentSheet shell; DetentSheet is used by ResultsSheet and AlternativesDrawer only) over the map. Sort pill: Fastest (default, `ROUTE_SORT_DEFAULT = 'duration'`), Earliest, Latest, By airline (`lib/routeResults.tsx:175-191`), via the iOS action sheet; date pill; Filters; Reset. The pinned card and bubble follow the chosen sort. The sheet no longer drags down when a scrolled list is pulled at the top: a drag that starts on a scrolled list gets 24 pt of travel before the sheet moves (`SHEET_HANDOVER_SLACK`, `components/DetentSheet.tsx:89, 353, 366-371`).
- Catchability (`lib/routeResults.tsx:491-560`): domestic catchable more than 1.5 h before departure, risky 1 to 1.5 h (amber "closing" tag plus "Check-in is close to closing and bag drop may already be shut."), uncatchable under 1 h or departed; international more than 3 h, risky 2 to 3 h, uncatchable under 2 h. Uncatchable flights go under a green "Active flights" heading after the other rows (`components/ResultsSheet.tsx:1205-1209, 1308-1311`); the heading covers flights inside the check-in cutoff as well as departed ones; they stay savable and are never "fastest". "Departed" flag from the server with a pre-departure-status veto.
- Board clocks: route rows, the map bubble, the answer line and the alternatives drawer all show the airport's zone now, from the airport dataset (commit d3a0c41; `lib/flightstatus.tsx:175-181`). A label is missing only when the airport or its time is unknown.

### 6.8 Connection search (server on the landing tag; UI in build 13)
- Settled spec: `docs/connection-search.md` (partly stale: it still says the app half is not started and that searches are never automatic; T16).
- Hubs: the intersection of origin A's destinations and destination B's destinations (B's destinations stand in for its origins), from AeroDataBox route lists (6 units each, cached 6 days in `routelists/`). Hubs more than 1.4 times out of the way are pruned before ranking (`DETOUR_MAX = 1.4`, great-circle via the hub over direct, coordinates from `airport_geo.py`). Ranked by the thinner leg's daily flights, ties by IATA code (`connections.py:456-478`). **No hub cap** (Jay: the fastest must really be the fastest). Branch-and-bound skips hub-days whose best possible journey (at 1,350 km/h) can't beat the best found. A 100-unit runaway guard (`UNIT_CEILING`, `connections.py:83`); an incomplete search never marks a connection "fastest" and the sheet says "N connections · not every hub was checked, so none is marked fastest" (`components/ResultsSheet.tsx:794-795`). Direct flights can still be marked fastest.
- Boards: leg 1 from A's board (usually cached from the direct search); leg 2 from each hub's dated board on the hub's local date; next day only if needed. Provider calls at 4 requests a second (per process), 3 boards at once (`PARALLEL_BOARDS`), shared bucket board cache.
- Pairing: each leg-1 flight with the earliest leg-2 that leaves at least 60 min (domestic) or 120 min (either leg international, or a country unknown) after it lands, within 24 h (the minimums are estimates and the code says so). One stop only. A first leg that has left or lacks an arrival time is dropped; a second leg with no arrival is skipped. Ranked by total journey time, capped at 25 (`MAX_ITINERARIES`), results cached 4 h in process memory, 30 min for a rolling search, complete searches only (`connections.py:109-110, 430, 659-660`). Codeshare dedup: a carrier match with the other leg wins, else alphabetical (for stability, not quality).
- Transfer label on every row, one text of up to two lines: an amber label, then its note. "Self-transfer" with "Separate bookings. Bags are not checked through and a delay is not protected."; or "Not a through-fare" with "Terminal built this connection; the airline may not sell it as one." (`lib/routeResults.tsx:407-414`). The server sends the second when both flight numbers share a carrier prefix, else the first. The map bubble shows the label only.
- Streaming NDJSON: a direct event first (the app ignores it), then a plan event (hub-days total), then per-hub events (each carries every itinerary through that hub so far) each followed by a progress event, then done. UI: "Finding connections", then "Finding connections · 3 of 13 checked", then "N connection(s)" or "No one-stop connections on this day"; on error "Could not load connections." with "Try connections again". Auto-start when no direct flight and the budget gate allows (§4.5), else "Show connections".
- Speed: cold Indore to Kochi went from 29.7 s to about 5.5 s; first results under 1 s [UNCONFIRMED: measured in the chat, not re-run].
- Row: both flight numbers ("6E123 + AI456"; the airline name only when one carrier flies both), journey ends in the large clocks with zones and "your time" on its own line, total time on the line, "via BLR · 1h" (the row uses the short form; the bubble prints "1h 00m"), "overnight" tag, transfer label. Map draws two arcs through the hub, bubble anchored at the hub, frame includes all three airports.
- Saving: the bookmark watches both legs (they appear as two unrelated watchlist rows). Long press opens the native iOS action sheet (`ActionSheetIOS`, `components/RouteRow.tsx:416-434`) titled "<first> + <second> via <hub>" with "Add to My Flights" (message "Saves both flights to My Flights as one trip.") or "Remove from My Flights": it looks up both legs (2 units each), saves them as one owned trip only if both lookups succeed, and undoes cleanly if the limit stops a leg. The card uses a glass panel instead (consistency question for the UI overhaul).
- Removed: "cheapest" sorting until a fare provider exists (Duffel is the v1.1 candidate; Jay floated Skyscanner APIs). Gemini's research suggested an offline OpenFlights graph and top-2 hubs; not taken.
- Jay saw several UI problems on an Indore to New York search but couldn't send screenshots (image limit). **Ask him what they were** (T17).

### 6.9 Alternatives drawer (disruptions)
- At a cancellation the server searches the next flights (§6.1 rules), classifies each (comfortable, at_risk, will_miss, unknown, none), and stores them. `/alternatives` (device_id plus X-Watch-Secret) returns them for owned flights only, with the identical answer `{"alternatives": null}` for flights the device doesn't own and for flights with nothing stored; a wrong secret gets the 404 (`api.py:1593-1623`, `store.py:377-407`). The device fetches when the drawer opens and never caches.
- Tapping a collapsed disrupted leg opens a drawer (not a screen) listing the next flights (`app/(tabs)/flights.tsx:2823-2826`). A disrupted leg that is the journey's current leg still renders as the expanded card with no drawer (Stage 5). Closing line: "These are the flights scheduled on this route. Terminal sees their times, not their seats or fares, and it books nothing." (`components/AlternativesDrawer.tsx:400-403`). The earlier "check with whoever holds your booking" line is gone (confirmed).
- Stages 1 to 4 done. Stage 5 pending: remove the expanded card for disrupted legs (compact card is the main thing), the next undisrupted leg expands, carry over refresh and map toggle, re-point the deep link; Home's different treatment accepted. Stage 6 pending: search from the diversion airport. "Rejoin further along" is gated on trip_id existing in watch rows.
- Jay's principle: a connection "isn't really gone" if there's a flight in 6+ hours; show it.
- Drawer look iterated: 15pt gap, G2 curves, more-rounded bottom corners matching the top, bottom text padding at rest. Jay's last words on it: "this should be below the nav bar", "first keep it below the nav bar or just revert", "but i wanna make changes later". Code today: the drawer is the last child of the My Flights screen, under the native tab bar, resting at 168 pt plus the bottom safe-area inset (`components/AlternativesDrawer.tsx:236`, `lib/sheet.ts:26-29`). [UNCONFIRMED: whether the inset includes the tab bar, so whether the drawer's resting edge clears it, needs a look on the phone.] What Jay means by "below": **ask Jay**.

### 6.10 Trip cards and disrupted cards (My Flights)
- The open trip card is borderless; collapsed leg rows still have a 1px hairline. Cards sit 8 pt apart (`CARD_GAP`); a layover row adds 10 pt above and below itself (18 pt around it). Layover duration at 15 pt (`app/(tabs)/flights.tsx:3830, 3851, 3878-3883`).
- Layover warning copy (`app/(tabs)/flights.tsx:1160-1170`): "Connection at risk (ideally 2h+)" or "This connection won't hold (ideally 2h+)", where N is the minimum (1 h domestic, 2 h international; a trip is international if any airport is in another country or unknown). International adds a long dash then "immigration and security might take time" (at risk) or "immigration and security will take longer" (won't hold); domestic has no immigration clause. Then optionally " · same terminal" or " · T1 to T2". A comfortable layover shows no warning. The warning stays after the first leg lands and goes when the next leg is no longer scheduled (open decision D4).
- Collapsed delayed card shows the "DELAYED 2H 25M" chip. The countdown to departure stays; no boarding-close countdown.
- Disrupted card layout: "LEG X OF X" (only with two or more legs); route top right (diverted shows "<origin> → <diversion airport>", or "?" when unknown); local day and date; CANCELLED or DIVERTED large (28 pt); flight number · airline on one line; "SCHEDULED DEPARTURE 14:35" now with the airport's zone and a "your time" line (open decision D5). Cancelled and diverted collapsed/expanded backgrounds must match; "cancelled" must not appear twice.
- Booking cancelled (a PNR-only cancellation email, no legs named): red. My Flights shows "BOOKING CANCELLED" with "Your airline cancelled this booking but did not say which flights." (`app/(tabs)/flights.tsx:1383, 1469-1470`). Home uses different wording: a "BOOKING CANCELLED · " chip with "airline says this booking is cancelled", a long dash, then "we cannot tell which legs" (`app/(tabs)/index.tsx:1070-1076`). The notice marks pending legs only; a booking whose legs were already saved shows nothing (`lib/saved.tsx:2637-2655`).
- Someone Jay showed it to couldn't tell which flight was cancelled; that drove making the compact card the main view (Stage 5).

### 6.11 Home, Deck, Profile, Gmail
- Home: search field, result card, watchlist (non-owned), Gmail pull row, pending legs (booked flights the airline hasn't published; retried on a schedule), Profile sheet. Header greeting and clock follow the phone's time zone today (`lib/flightstatus.tsx:100-104`, `app/(tabs)/index.tsx:269-285`). Planned: follow the trip's city, switching to the destination from 30 min before the latest expected arrival; approved to build, **not started** (T12). Beta complaint: after landing it still showed San Francisco time.
- Deck: derives the airport from the journey (manual pick overrides), layover reserve (estimates), dining split by security side, terminal schematic where data exists.
- Profile: SwiftUI formSheet (@expo/ui); Google sign-in; Log out; two `__DEV__`-only sections: "Dev only · fake disruptions" (13 scenarios and a Clear fixtures button) and "Dev only · website screenshots" (11 shots; its footer says to clear fixtures when done) (`app/profile.tsx:550-608`).
- Gmail import: Gemini extraction from HTML, text, PDF tickets and JSON-LD, codeshares, multi-leg; lists up to 40 emails and reads up to 25 (`gmail_flights.py:87-89`); cancellations and changes applied oldest to newest; cancellation sticky; a PNR-only cancellation becomes a booking notice (not sticky: a later confirmation under the same reference withdraws it). The beta tester had no flights in Gmail, so hers were added by hand.
- Change emails: the server now retires the leg a change email names (commit 084c55a; `gmail_flights.py:1418-1464`), but only when the email names the replaced flight. The app's auto-add saves any leg the provider can find whatever the server's status says (`lib/gmailPull.tsx:221-298`), so a retired leg whose flight still operates could still be saved next to the new one [from reading the code, not tested].
- Logging in and out: flights are stored per account on the device (`lib/storage.ts:4-5, 609-611`); guest flights merge into the account on sign-in; a flight saved while signed in stays with the account (Jay insisted). There is no server-side account store. A "flights disappear on login" report resolved itself [UNCONFIRMED: root cause not identified].

### 6.12 Dev fixtures
- "Terminal Test Air" ZZ9xx fixtures on a BOM → DEL → BLR → DXB trip for disruption states (`lib/devFixtures.ts:39, 185, 244-296, 390-590`): all comfortable, connection at risk, connection missed, leg 1 cancelled, leg 2 diverted (DEL to HYD), booking cancelled with legs unknown, in the air, landed with a belt, and five departure states (12 min past and still at the gate, announced 45 min late, left the gate 18 min late, FR24 saw it take off, record 40 min old). Profile → Dev only · fake disruptions.
- Website screenshot fixtures: BA177 Heathrow to New York (five states), BA286 San Francisco to London then LX325 London to Zurich (six states), made-up next flights (`SITE_SHOTS`, 11 entries). Profile → Dev only · website screenshots. Their notification texts follow the final wording (commit 1fb4d75).
- **Not compiled out of release:** the Profile rows and `devSetFixtures` are `__DEV__`-only, but `lib/devFixtures.ts` is imported unconditionally by `lib/saved.tsx`, `lib/watch.ts` and `lib/alternatives.ts`, so it ships in release builds, contrary to comments saying it doesn't (T10). Fixtures mostly never touch the network, with the registration gaps in §6.2.
- No ZZ9xx rows are left in watches.json (confirmed).

### 6.13 Map (GlobeMap, MapLibre in a WebView)
[UNCONFIRMED: this section is from the chat and was not checked on a device.]
- Iterated heavily. Jay's requirements: looks black, not washed out; no grey land; borders subtle (not white or bold; he asked three times); no circles over cities; roads visible; fast loading; depth he can see. Tried and reverted: grey land, green borders, invisible sea depth, dark marine blue water, heavy relief.
- Open bug: stray lines near the poles ("random lines").
- He called the map "the most non-iOS looking thing". Options on the Mac: polish MapLibre further or use Apple Maps; he leaned to fixing the existing map. Mapbox is planned for indoor maps later (native SDK, a Swift module; @rnmapbox/maps had a known Xcode 26 build failure with the floor selector).

### 6.14 Website (new design, not deployed)
- Off-white page, black final section and footer. Structure: hero, a phone showing My Flights with a notification arriving, three moments (something changes: gate, delay, takeoff, landing, belt; a delay threatens your connection: comfortable, at risk, won't hold; a cancellation: next flights already listed, Terminal doesn't book), why it's different (airport knowledge with the "604 places at seven airports" dining table; confirmation emails become trips; it doesn't know who you are), close, footer. Hero line in the repo: "When a flight is cancelled, Terminal shows which next one still makes your connection." (`index.html:58`).
- Removed on Jay's instruction (confirmed absent): "Free, for iPhone.", "What it reads, in full", booking language (it's "confirmation emails" now), "Terminal's server keeps no name or email", the carved TERMINAL wordmark and the horizontal line; the footer stays its original size.
- Added: the contact email on every page, "Coming to the App Store" (once on the home page and once on each other page; a label until launch, then Apple's badge), @Jayo10o on X (`index.html:37, 169`), a departure board that flips every 5 seconds (`assets/board.js:28`), hover states, support page, 404.
- Phones are placeholders until real screenshots after the UI overhaul (image descriptions say "Placeholder for Site N"). Apple's bezel artwork rules: phone shown whole, flat, no crop, no shadow, nothing overlaid, real status bar.
- The search section is not in the committed site at all, hidden or otherwise. [UNCONFIRMED: where the drafted section lives, if anywhere.] It stays out until the build with the new search ships, and its example phrase must be run through the shipped build first.
- Outstanding: og.png still shows the old black design and the old wording ("Your flight to London has moved to gate 7, was 12."); privacy, terms, support and 404 load the older stylesheet (`site.css`, the home page uses `page.css`) [UNCONFIRMED: how different they look]; the hero sub-line says two-minute checks happen "in the last ninety minutes" (`index.html:59`) and support.html:37 says every 10 minutes in the last six hours, both wrong once the GATE tier is live (T16); deploy only after screenshots and after the new server wording is live; web analytics (Jay wants visitor counts; the privacy policy says the site sets no cookies and loads nothing from any other site, so any analytics choice must keep that true or update the policy).
- Privacy policy points (confirmed in `privacy.html`): server region asia-south1 in India; diagnostic records and schedule caches disclosed; "Log out" in Profile to disconnect. The corrected sentence "Our server reads them from Google once, as you sign in, passes them to your phone, and keeps neither." is in the repo (`privacy.html:41`) and not on the live site. The route-list line says "Lists of the flights between two airports" where a route list is one airport's destinations (`privacy.html:55`).
- Google's Gmail review expects the home page to explain Gmail use; the home page doesn't name Gmail. Moot if Gmail reading is replaced by a forwarding address.
- Deploy: `cd website && vercel --prod --yes` [UNCONFIRMED: not run]. The Vercel link (`.vercel/`, git-ignored) moved with the folder.
- X (@Jayo10o) posts so far: the airport maps backend (JFK, LHR, BOM), the domain and email, the search fixes, and connection search "in the backend". Rules for posts: no Indian data, no provider names, no OpenStreetMap; show the thinking and the backend, not UI explanations, when that's what Jay asks for.
- Shot list (on iPhone 17, from Claude Code): battery 100% and unplugged, full bars, Low Power off, no Focus, nothing in the Dynamic Island, notifications allowed with Summarize off, time zone set to London, shoot between about 09:00 and 16:00 London time; Profile → Dev only · website screenshots → tap the shot → close the sheet → go to the named tab; shot A immediately, the notification arrives 10 s later for shot B. Shots 1 to 5 BA177 gate changed, delayed, in the air, landed, bags on belt 9 (My Flights, A and B); 6 trip layover comfortable (one); 7 connection at risk (A, B); 8 won't hold (A, B); 9 BA286 cancelled (A, B, then C with the drawer open); 10 on the layover in London (Deck, where to eat at Heathrow); 11 just imported ("added BA286 +1 more · undo", don't tap undo). Afterwards: Clear fixtures, time zone back to automatic. Banner shots need the real app icon first.

---

## 7. Problems solved in this chat (so nobody re-diagnoses them)
Direct AeroDataBox migration; key hygiene after the key.txt incident; orphan state files (deleted 26 h after their last watch goes); a stuck flight state of the QP1149 kind (state that never finished); sign-out deregistration; typed dates on flight-number search (and past dates); PNR-only cancellation notice; map contrast, relief and coastline; catchability bands; connection search (server and UI); alternatives drawer stages 1 to 4; minute refresh via /watched; diversion airport from FR24; timezone labels everywhere, including board clocks; world-wide smart search; departure delay count; landing summary, expiry and collapse IDs; notification wording; website redesign; notification tap opening the right day's card; splash screen always hides on a notification cold start; a cold-start notification tap is handled once and waits for the navigator (`app/_layout.tsx:97-117, 204-301, 414-421`).

## 7a. Decisions log (what was decided, and why)
- Moved AeroDataBox from RapidAPI (5,000 units, exhausted) to the direct plan (40,000 units) and cancelled RapidAPI. A single request helper with a 401/403-only fallback; 429 never falls back (it would double spend). The fallback now has no key set, so it is dead.
- Poll faster (DAY 10 min, NEAR 2 min, AIRBORNE 5 min) because Jay can afford it now; then 2-minute checks from 4 h before departure because a gate change reached the beta tester 20 minutes late. Built as a new GATE tier (4 h to 90 min, AeroDataBox only), with NEAR unchanged.
- Minute-by-minute foreground refresh from the poller's stored data instead of spending units per phone.
- Label "updated X ago", per Jay (it shows the later of the app's fetch and the provider's data time).
- Stop live refresh at landed + 45 min, or when the belt appears after landing; a belt before landing no longer stops it (the belt fix).
- Connection search: no hub cap (truthful "fastest"), speed via parallelism and branch-and-bound instead; automatic start guarded by a server budget threshold, not a per-device cap.
- Catchability thresholds 1 h domestic / 2 h international, with a risky band and a reason line; not factoring travel time to the airport.
- Alternatives are searched by the server at cancellation and shown when the card is tapped; the user doesn't search.
- Next-flight window one week max. The code offers any flight leaving at least 90 minutes after the moment of the search, including one before the cancelled flight's own time (see §6.1).
- Leaving the gate is display only, not a push. The FR24 one-minute watch waits for Stage 2 measurements.
- Diversion only in flight; diversion airport from FR24.
- No boarding-close countdown; no estimates.
- Notification titles: route + number, city names within 26 characters.
- Landing figure from touchdown.
- Collapse IDs on superseding kinds.
- Email: Google Workspace (not Zoho) on terminalaero.com.
- Domain: terminalaero.com (terminal.com and terminalapp taken; "Terminal Aero" vs "Aero Terminal" discussed; he bought terminalaero.com).
- Gmail restricted scope: avoid CASA; move to a forwarding address.
- Keep MapLibre and polish it for now; Swift/native for cards and interactive pieces on the Mac ("I won't make it fully swift but all the cards, interactive things will probably use swift").
- Tab-wide drawer over a shared black background: wait for the Mac.
- Website: light theme, not Flighty-like, real screenshots only.
- Traffic moves once, after the beta trip, with everything in one revision.

(Private details are kept in the Project copy, not in this repo.)

---

## 9. The beta trip and what it taught us

Three legs, one tester on build 12, two more devices watching as meeting (§5.4). Times below are from the server's diagnostic records and stored state.
- **Leg 1**, long-haul from the US West Coast to Amsterdam. Left the gate 11 min late; FR24 saw it take off 37 min after the scheduled departure; touched down about 12 min early. The belt was published in flight (three changes, final belt 10).
- **Leg 2**, long-haul Amsterdam to Mumbai, landing just after midnight IST. Gate E2 first seen the evening before (19:56:04 UTC); gate E6 first seen 08:12:05 UTC on departure day; push decided 08:16:04, sent 08:17:02 UTC, Expo receipt "ok" on all three watching devices. The provider published a Mumbai belt ("4") at 03:58:04 UTC, about 20 h before landing; it changed to 10 in flight. Her phone's last live refresh for this leg was at 08:03:59 UTC, and it made no /watched request at all between 08:05 and 12:00 UTC (Cloud Run request logs). Landed 00:01:58 IST (FR24); the landing summary went to all three devices at 18:35:01 UTC.
- **Leg 3**, domestic Mumbai to Indore the next morning. No live coverage expected.

(Private details are kept in the Project copy, not in this repo.)

What went wrong, and where each fix lives:
| Problem seen | Cause | Fix | Where |
|---|---|---|---|
| Leg 1 still "scheduled" long after it left the gate, no delay shown | No "left the gate / delayed" state; poll data lagged (the provider's status turned active 40 min after the gate time); FR24 takeoff not used by the app | Departure delay count; FR24 takeoff as proof | App: build 13. Server: FR24 proof already in; Stage 2 for gate-out/takeoff events |
| Delay shown only once airborne | Same | Delay counts every minute until the runway | Build 13 |
| After landing, times still in San Francisco time | Clocks followed the phone's zone, no airport labels | Zone labels + "your time" (built); header clock follows trip city (not started, T12) | Build 13 |
| Landed leg 1 card at Amsterdam still said "gates closing" until she refreshed by hand | Stale card after landing; refresh on build 12 not recovering [UNCONFIRMED: app-side; the diag records cover the server only] | /watched + landing handling; belt fix | Build 13 |
| No auto refresh; gate change E2→E6 not shown live | Build 12 stops the minute refresh once a belt exists; the provider published the Mumbai belt 20 h early, so refresh stopped after 08:03:59 UTC (confirmed in request logs) | App ignores a belt before landing; server never sends a belt before landing | Build 13; server 00122 (commit 4160c21) |
| Gate change push arrived about 20 min late | DAY tier checked every 10 min until 90 min before departure, then the change had to hold two polls | 2-min checks from 4 h before departure (GATE tier) | Server 00122 (commit 986bc0c) |
| Gate change message "garbage" (Jay's word) | Old wording repeated the title, awkward | New titles and one-line bodies | Server 00122 |
| "Time to leave" fired for connecting flights | Reminder not limited to the first leg | First leg only; connecting-leg reminders | Not started (T13) |
| "Took off" push on gate time | notify.py uses gate-out | FR24 Stage 2 | Pending |
| Tester said "your app is not taking the timezone" | Same as the clock issue (possibly also unfamiliar UI) | As above | Build 13 |

After the trip: read the diag/ records for all three legs while they still hold values, compare what happened with what the app and pushes showed, then clear the diagnostics as part of the traffic move (T3, T5).

---

## 10. Security and secrets
- The repo is public (confirmed): never commit secrets, the bezel artwork, personal data, or this doc's private blocks.
- In Secret Manager: aerodatabox-api-key, token-key, gemini-api-key. Plain setting values (confirmed): FR24_API_TOKEN, WATCH_SECRET, POLL_SECRET, DISPATCH_SECRET, ALERT_WEBHOOK_SECRET, ALERT_READ_SECRET.
- Incident: a key.txt file got baked into a deployed image. Fixed: file deleted, `key.txt` and `*.key` in `.gitignore` and `.dockerignore` (confirmed), redeployed, the affected image deleted (confirmed absent from the registry), Cloud Build source archive deleted [UNCONFIRMED: not re-checked].
- Incident: a Claude Code env dump printed secret values to a terminal (not repeated anywhere). Hence "names only".
- Not rotated [UNCONFIRMED: rotation state not visible]: FR24 token (rotate on the Mac; Jay: "no one has the access to that"); WATCH_SECRET (ships inside the app binary as EXPO_PUBLIC_WATCH_SECRET, so rotation is pointless; the real fix is securing /watch with a session token); the dispatch secret and a fixture token were also listed as unrotated earlier.
- `send_gmail_tests.py` is untracked and in no ignore file. It sits at the repo root, outside `server/`, so a deploy from `server/` can't upload it, and `server/.gcloudignore` keeps keys, `.env`, caches and the airport snapshot out of the upload. Before the restructure the server deployed from the repo root and the Dockerfile copied everything: revision 00107's upload included it and `.claude/settings.local.json`. It reads its credentials from the environment rather than holding them. Deploy from a clean worktree; delete the old bundles and images that carried it (T8).
- Old Project notes also said the landing provider's token was once pasted into a chat.

(Private details are kept in the Project copy, not in this repo.)

---

(Private details are kept in the Project copy, not in this repo.)

---

## 12. Open bugs and known faults
1. "Took off" push fires on the gate-out time (`notify.py:384, 566-577`). Stage 2.
2. Build 12 stops auto refresh once a belt exists (fixed for build 13 and on 00122).
3. `lib/storage.ts`: normalizeRecord pins every record at schema 11 while `SCHEMA_VERSION` is 15 (`lib/storage.ts:7, 600-603`), so the v12 and v13 upgrades run again and every non-empty saved list is written back on every read (`lib/storage.ts:514-533, 641-644`). Two overlapping read/write cycles can lose the newer save. Records aren't corrupted. The comment describing the fault says 13 (stale), and `lib/devFixtures.ts:215-217` wrongly says normalizeRecord leaves version 15 alone (T11).
4. Jay's own install id is not proven current (T2).
5. `lib/devFixtures.ts` ships in release builds; fixture registration has gaps (§6.2, §6.12, T10).
6. On narrow phones a row with both zone labels may truncate; "your time" is always the last segment of the line, so it is what gets cut (by design, `lib/flightstatus.tsx:483-484`). Not checked on a device.
7. Map: stray lines near the poles [UNCONFIRMED: not checked on a device].
8. Connection row long-press uses the iOS action sheet; the card uses a glass panel.
9. Twice-daily flight numbers could be promoted by an earlier rotation; guarded by the 1-hour rule on the server (`poller.py:216`) and in the app (`EARLY_SLACK_MS`, `lib/departure.ts:28-36`), not eliminated.
10. Doha arrivals often get no FR24 landing (accepted).
11. Gmail: a change email that doesn't name the replaced flight leaves the old leg; and the app's auto-add can save a retired leg whose flight still operates (§6.11). The splash-screen and cold-start notification-tap bugs are fixed (§7).
12. @expo/ui constraint for the Swift work: don't put an RNHostView inside a SwiftUI conditional (a known crash family); mount hosts unconditionally or navigate to RN screens instead. ScrollViewMarker must keep resolving the scroll view or the tab bar's minimise-on-scroll and scroll-to-top silently stop. [UNCONFIRMED: not re-checked.]
13. `android/.env.local` points dev builds at an old tag.
14. Apple stores one offline notification per app; long flights lose all but one push (mitigated by the landing summary).
15. No script in the repo calls gsutil, so the gsutil deprecation (March 2027) only affects personal scripts.
16. After a cancellation tap the route list opens sorted Fastest though the server asks for earliest (open decision D6).
17. The booking-cancelled notice uses different wording on Home and My Flights, and marks pending legs only (§6.10).
18. A connection's wait prints "1h" on the row and "1h 00m" on the map bubble (§6.8).
19. Stale docs and comments: DEPLOY.md, `docs/connection-search.md`, `pollstate.py:587` (says the reset is on the 7th), the 500-unit reserve premise, several "cap is 20" comments, "#050505" comments, DetentSheet's mode comment (T16).

---

## 13. Tried and rejected (don't redo without a new reason)
- Per-device daily cap on connection searches.
- Capping hubs (top 2 or top 4).
- "Cheapest" sort without fares.
- Boarding or gate-close countdowns; any estimated time shown as fact.
- Pull-to-refresh (but the code has it today: open decision D1).
- Forced model retry for search; the two-press "did you mean" reading.
- Zoho Mail.
- Map: grey land, green borders, marine blue water, heavy relief; carved TERMINAL wordmark on the website.
- OpenSky/ADS-B as a data source: Indore returned no aircraft at all and Mumbai's positions were minutes stale (coverage gap).
- A native iOS formSheet for route results (a custom DetentSheet was used instead).

---

## 14. Commits on native-ios-tabs since 9 September (129 commits, 9 to 24 September, all pushed)
Grouped from `git log`; no commits on 10 or 11 September.
- **Server, push:** outbox sent through Expo with its own dispatch secret; stale messages dropped with a reason; a finished flight isn't held open; expiry per kind, collapse IDs and the landing summary (85eb22d, d6d001b, d9f5bc0, d4d30c2, ca1932d).
- **Server, poller:** FR24 takeoff as a departure proof; landing without a gate time ends polling; state objects deleted after DONE and an orphan sweep; faster tiers plus /watched; GATE tier; belt held until landing (5486ecf, 902383b, 5eba7c5, 22a633c, 9b3de83, 986bc0c, 4160c21).
- **Server, notifications:** connection-risk push; nothing sends the reader to the airline; alternatives found on cancellation; a diversion names where the flight landed; short wording, then route titles and personal bodies (ab75c28, 5de8e4f, 821975d, 6d0749c, c6652f5, fc92472).
- **Server, providers:** AeroDataBox direct, RapidAPI retired, key file out of the image, board rows say whether the flight has departed (a318571, 78ea544, b0a3296).
- **Server, Gmail extraction:** classify before reading, newest email wins, attachments read, cancellation by booking reference, change email retires a leg (f2050e6, 7907657, d850775, e27a833, 084c55a, dc542e0, 15fe85b).
- **Server, search and connections:** /intent in one press, questions as intents, routes in any language; connection search with streaming and the budget gate (1ed3f38, 8335603, 76bc85c, a5cb8eb, b084d2e).
- **App, trips and Gmail pull:** pending and unpublished legs in their journeys, layover rows, cancelled legs (most 9 Sep commits).
- **App, surfaces:** native Profile sheet; results sheet the app owns, sort default Fastest, catchability; overscroll fix; map coastline, relief, sea depth and credits (87e3db6, 77cb39b, 227569d, f6175e4, 86a2d96, 146a86d to fced6f9).
- **App, disruption:** disrupted cards, the alternatives drawer, layover warnings, fixtures, contrast and corners (1f838a6, bd392b6, b648a20, 7301d4b, a3a3fc5, 9c7255d, 217526a).
- **App, live data:** taps open the flight; saved flights carry the push token; sign-out stops watching; /watched live refresh; zone-labelled clocks with "your time"; departure delay count; landed early or late; belt refresh fix (a2a3208, e056639, 86648ba, 92edb9d, 70d1897, d3a0c41, 01936ba, 26cf12b, 4160c21).
- **App, search:** typo-tolerant resolver, one-press command line, world names in many scripts, Santiago picker, typed dates, 6E carrier codes, connection search UI (47795eb, 57a9c08, b6b46c6, 37d73d1, 98ebebe, 53376c8, 15dab2b).
- **App, platform:** iOS 26 floor, Terminal name, dark splash, submit without a person, dev menu screenshots (503f99d, 520ca58, 34b097f, e8f77a6, 1fb4d75).
- **Website:** privacy for attachments; new cancellation-led design, not deployed (d850775, f706569).
- **Tests:** cache test pinned; pending-rules clock; three extra booking fixtures (4e641f1, a711782, 6a4f8b2).
- **Docs:** context doc updates, RapidAPI deploy notes, connection search spec, schema pin note, background refresher note (e73a0ad, bc393ea, c03e790, e7e9bba, 84dc6df, d1e443d).

---

## 15. Mac setup (25 September)
1. Install Xcode (and its command line tools), Homebrew, Node (LTS), Python 3.12 (the server image is `python:3.12-slim`), git, Google Cloud CLI, eas-cli, Vercel CLI, VS Code, Claude Code.
2. Clone the repo into a normal folder (for example ~/dev), **not** iCloud Drive or any synced folder (OneDrive caused Metro failures on Windows). Check out native-ios-tabs.
3. Copy the root .env and the app's .env (now `android/.env`) from the carried copy. Do not copy .env.local. Keep send_gmail_tests.py outside the repo or ignored. Keep the bezel PNG out of git. `android/.env`'s watch secret must also go into EAS for build 13 (T9).
4. Log in: GitHub, `gcloud auth login` and set the project, `eas login`, `vercel login`, Apple ID in Xcode.
5. Install dependencies; start the dev client; confirm the phone connects.
6. Rotate the FR24 token (move it to Secret Manager while at it), then wipe the carried copy and delete the secret files on the PC.
7. Day plan: day 1 setup, app icon (Icon Composer), design system written from the website's rules; day 2 screens for screenshots; day 3 rest, then shoot (through Sunday 28 Sep). Main goal for these days: fix all of the app's UI, including everything that goes into the screenshots.
8. Gemini UI audit: a full UI audit prompt was written for Gemini (terminal-ui-audit-prompt.md); feed its answer into the overhaul. [UNCONFIRMED: the file is not in the repo; whether Jay ran it is unknown.]

---

## 16. Roadmap

### Launch blockers (before App Store submission, late October)
- In-app account deletion (Apple requires it when accounts exist).
- Secure /watch with the session instead of the shipped secret.
- Move watches.json to a database (Firestore suggested); needed also for trip history.
- Email import by forwarding (a forwarding address on terminalaero.com via Cloudflare Email Routing) instead of the Gmail restricted scope. Decide what sign-in remains; check Apple's rule on offering Sign in with Apple when a third-party login exists [UNCONFIRMED: current guideline 4.8].
- Crash reporting (Sentry, free tier).
- App icon; App Store listing, privacy labels, screenshots, support URL, review notes; export-compliance answer.
- Release hygiene: the Dev only rows are already `__DEV__`-only; stop `lib/devFixtures.ts` shipping (T10); expo-dev-client out of production dependencies; separate dev bundle id.
- Freeze v1 scope.
- Merge native-ios-tabs into `master` (the default branch; there is no `main`).

### Next features
- FR24 Stage 2: measure flight events and live positions (latency, credits), one-minute watch from boarding/scheduled time to takeoff, fix "Took off", send gate-out and takeoff to the app; later predict delays from the inbound aircraft.
- Alternatives drawer Stages 5 and 6; disruption notifications for alternatives.
- "Get what you're owed": entitlements (EU261, India's DGCA rules, US DOT refunds), claim drafting, persistence after the trip.
- Connection search: fix the UI problems Jay saw; offline curated route lists for the busiest hubs (6-day refresh); revisit the 500-unit reserve.
- Trip history ("Passport", like Flighty but more); aircraft type needs an answer from AeroDataBox.

### Later
Mapbox map and indoor maps; Live Activities and Dynamic Island (likely the first real Swift); widgets; App Intents; Apple Watch; brightness-aware palette; contrast second pass; map pole streaks; booking and cheapest via Duffel (v1.1; roadmap said November); Android (December/January); product analytics (PostHog) and web analytics.

### Notes for the UI overhaul (from Claude Code's earlier research) [UNCONFIRMED: not re-checked]
> Note: written for the React Native app's @expo/ui path, which the Swift rebuild replaces (`docs/SWIFT-REBUILD.md`).
- @expo/ui SwiftUI can do: native countdowns that tick without JavaScript (Text with a timer interval, monospaced digits, numeric transitions), JetBrains Mono by its PostScript name (check on device), Sections, LabeledContent, ContentUnavailableView for empty states, swipe actions (only inside a List, which brings its own insets and replaces the card look), and formSheet routes like Profile.
- @expo/ui can't do: arbitrary paths or canvas, so FlightCard's progress arc and similar drawings need real Swift (a native module) or stay in React Native. The swipe rows' custom physics (friction, expand threshold, haptic, throw-off) become Apple's standard swipe if ported.
- Safest boundary: whole screens or whole sections in SwiftUI; anything SwiftUI can't draw is navigated to, not embedded. If a React Native view must sit inside SwiftUI, mount its host unconditionally.
- A tab-wide drawer is possible: NativeTabs can live inside a height-animated drawer (the tab bar sits at the drawer's bottom edge); risk is jank from relayout on every drag frame, with a per-tab drawer as the fallback. Search would become a modal opened from the search pill. Open design choice: drawer surface one elevation step up (#151515) with every card one step up too, or page black with cards unchanged.
- Home redesign idea explored: an "active" hero card for your next flight (this reverses the rule that owned flights live only in My Flights, so decide deliberately) and a "standby" card for the nearby airport (needs location consent, which today is only asked in Search; Home must not become a second place that prompts). Hand off to Deck rather than duplicate it.

### Claude Code cloud credit plan
First a CLAUDE.md, a single check command that runs every suite, and a setup script. Then one well-scoped server task per session: account deletion, secure /watch, forwarding import, database move. No UI, no deploys, no secrets in the cloud.
(Private details are kept in the Project copy, not in this repo.)

---

## 17. Tasks in priority order
The full task list, with why, steps, done-when and constraints for each, is `docs/TASKS.md`. In short:
T0a data accuracy investigation (deadline 29 September); T0b Swift rebuild (`docs/SWIFT-REBUILD.md`); T1 beta tester push check; T2 identify which install is on which phone; T3 move live traffic and clear the diagnostics in the same step; T4 pay Google Workspace; T5 review the diagnostic records; T6 Mac setup and FR24 token rotation; T7 housekeeping and deploy ignore files; T8 delete old source bundles and images (approval first); T9 build 13 watch secret; T10 dev fixtures out of release; T11 storage fault; T12 header clock and greeting follow the trip's city; T13 "time to leave" for the first leg only, plus connecting-leg reminders; T14 reminder wording; T15 open decisions D1 to D6; T16 stale docs and copy; T17 the Indore to New York connection UI problems; T18 UI overhaul week; T19 screenshots, then website; T20 build 13 to TestFlight, then retire /parse and /chat; T21 a tester's TestFlight install; T22 launch blockers; T23 FR24 Stage 2; T24 alternatives Stages 5 and 6, disruption notifications, "get what you're owed"; T25 credits follow-up; T26 repo hygiene; T27 small fixes found in verification.
(Private details are kept in the Project copy, not in this repo.)

---

## 18. Open questions waiting on someone
- AeroDataBox: device storage beyond 7 days (§3.6); aircraft type for flight history. Jay doesn't want to email them again for now.
- Anthropic: startup credits.
- Jay: the six open decisions D1 to D6 (§2.4); IDR to NYC UI problems; the alternatives drawer's final position; new connection reserve figure; whether Sign in with Apple is needed. Decided already: leaving the gate is display only; the FR24 one-minute watch waits for the Stage 2 measurements.
- Website approvals: the repo has the hero line "When a flight is cancelled, Terminal shows which next one still makes your connection." and the corrected privacy sentence; the live site has neither (it still serves the old design).
