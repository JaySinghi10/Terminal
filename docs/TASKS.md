# Terminal: task list

Verified against the repo (commit 1fb4d75), the Cloud Run service and the bucket on 25 September 2026. Priority order, top first. Background for every task is in `docs/HANDOVER.md`; section numbers below point there.

Rules that apply to every task:
- Read the relevant files first, show the diff, wait for Jay's approval before applying.
- Run all eleven server test suites before any server commit; for the app, `tsc` clean, no new eslint problems, and the node tools in `FlightTrackerApp/tools/` that apply.
- Deploy only to a no-traffic tag, from a clean git worktree of the commit. Never move traffic without Jay. Settings change with `--update-env-vars` and `--remove-env-vars`, never `--set-env-vars`.
- Never print a secret value or a push token. Cloud Run settings: names only.
- Test pushes go only to Jay's own device (T2 confirms which install that is).
- Private details (people, device ids, dates of the beta trip, money) are kept in the Project copy of the handover, not in this repo.

---

## T1. Ask the beta tester whether the test push arrived
- **Why:** a test push was sent to the beta tester's phone with Jay's approval, and its Expo receipt has expired (Expo's getReceipts returned nothing on 25 September), so the server can no longer say whether it was delivered.
- **Steps:** ask her. Separately, read the last leg's diagnostic record for the delivery stages of the landing summary (its receipt was still pending when checked).
- **Done when:** the answer is recorded in the Project copy.
- **Constraints:** no new push to her phone.

## T2. Identify which install is on which phone
- **Why:** test pushes must reach Jay's phone only, and the install believed to be his has not written a watch row since 9 September. Two other installs watch the beta legs as "meeting", one of them unknown to the handover (§5.4, Project copy).
- **Steps:** on each phone, save a distinct flight nobody else watches, then list `watches.json` rows for that flight number with device ids only (never tokens). Record which install is Jay's, which is the other known device, and whose the third is.
- **Done when:** the three installs are named in the Project copy, and Jay's install id is confirmed current.
- **Constraints:** ids go in the Project copy only, never in the repo. Read-only on the server except the watch rows the phones write themselves.

## T3. Move live traffic to the landing revision, clearing the diagnostics in the same step
- **Why:** the live revision (00114, commit 76bc85c) lacks everything built after that commit. The landing revision (00122) is proven identical to commit 1fb4d75. The diagnostics must stop after the beta trip, and clearing `DIAG_FLIGHTS` on its own no longer works: the service template is now 00122's image, so a settings change creates a new revision from 00122's code with 0% traffic while 00114 keeps recording (§4.1, §4.4).
- **Licence check (done during verification):** the 6-day value strip and 30-day deletion of diagnostic records run on every poll pass whether or not `DIAG_FLIGHTS` is set (`poller.py:1159-1163`, `diag.py:290-323`). They are skipped only if the bucket or the watch store can't be read. So clearing the setting does not stop the licence clean-up, provided the poll scheduler keeps running for at least 30 days after the last record was created.
- **Steps:**
  1. Only after the beta trip is over (time in the Project copy) and Jay approves the timing.
  2. List revisions with tags and traffic. Confirm the `landing` tag is still on `flight-tracker-00122-nay` and that `native-ios-tabs` has no server commits after 1fb4d75. If HEAD has moved, deploy HEAD to a fresh tag from a clean worktree, run all suites, and use that instead.
  3. Create the candidate: `gcloud run services update flight-tracker --region asia-south1 --project flight-tracker-496006 --remove-env-vars DIAG_FLIGHTS,DIAG_DEVICE --no-traffic --tag live` (or another tag name Jay picks). This makes a new revision from the service template.
  4. Confirm the new revision runs the same image as 00122 (compare the image digests) and that its setting names are 00122's minus the two diagnostic names (names only).
  5. Smoke-test the tag URL: `/quota` (gateway "direct"), one `/flight`, one `/connections`.
  6. Jay approves the move. Move 100% to the new revision by name: `--to-revisions=<new revision name>=100`. Never `--to-latest`.
  7. Verify for 10 minutes: `/poll` and `/dispatch` return 200 in the logs, `/quota` reports the direct gateway, one test push reaches Jay's device only (T2 first).
  8. Rollback if needed: 100% back to `flight-tracker-00114-jev` (this brings the diagnostics back until the next attempt).
  9. Then remove the stale tags (`intent-eval`, `connections`, `wording`), keeping only meaningful ones.
- **Done when:** 100% of traffic is on a revision built from the verified commit with no `DIAG_FLIGHTS` or `DIAG_DEVICE`, pushes and polls are healthy, and stale tags are gone.
- **Constraints:** never print setting values; never use `--set-env-vars`; the poll scheduler must keep running (the diagnostic sweep depends on it).

## T4. Pay for Google Workspace before the trial ends
- **Why:** the work mailbox stops if the trial lapses.
- **Steps:** Jay completes payment in the Workspace admin console; check whether the console warnings are cleared.
- **Done when:** the mailbox is on a paid plan. (Plan, price and trial date in the Project copy.)

## T5. Review the diagnostic records for the three beta legs
- **Why:** provider values in the records are stripped six days after each event; after that only the skeleton of what the server did remains.
- **Steps:** read `diag/` for the three legs; compare every poll, decision and delivery stage with what the app and pushes showed on the trip (§9). Note anything the handover's §9 table doesn't explain.
- **Done when:** a short written review exists (in the Project copy if it names the legs).
- **Constraints:** read-only. The deadline is in the Project copy.

## T6. Mac setup, then rotate the FR24 token
- **Why:** development moves to the Mac; the FR24 token has never been rotated and is a plain setting.
- **Steps:** follow §15. Rotate the FR24 token and move it to Secret Manager (a settings change on a no-traffic revision, then the next traffic move). Then wipe the carried copy of the secrets and delete the secret files on the PC.
- **Done when:** the dev client runs from the Mac, the new token is live, and no old copy of the secrets remains.
- **Constraints:** never print the token; settings changes follow the T3 pattern (new revision, check, move by name).

## T7. Housekeeping and deploy ignore files
- **Why:** `send_gmail_tests.py` is in no ignore file and there is no `.gcloudignore`, so a deploy from the main working tree uploads it and the Dockerfile copies it into the image (revision 00107's upload included it and `.claude/settings.local.json`).
- **Steps:** add `send_gmail_tests.py` and `.claude/` to `.dockerignore`; add a `.gcloudignore` that covers the same files plus the app and website folders the server doesn't need (check the upload list with `gcloud meta list-files-for-upload` before and after). On Windows: delete `FlightTrackerApp/.env.local`, the secret files, the leftover temporary worktree folder, and empty the OneDrive recycle bin (paths in the Project copy).
- **Done when:** the upload list from the main working tree no longer contains those files, and the Windows leftovers are gone.

## T8. Delete old source bundles and images that carried private files
- **Why:** revision 00107's source bundle and image include `send_gmail_tests.py` and `.claude/settings.local.json`.
- **Steps:** list every source bundle in the Cloud Run sources bucket and every image in the Artifact Registry repository that contains either file (check by content, not by name). Show the list with the revisions that use each, and wait for Jay's approval. Only then delete. Do not delete anything a serving or tagged revision uses.
- **Done when:** no stored bundle or image contains those files, and every tagged or serving revision still starts.
- **Constraints:** approval before any deletion; deleting a revision's image means that revision can never be rolled back to.

## T9. Build 13: supply the watch secret to EAS
- **Why:** `EXPO_PUBLIC_WATCH_SECRET` exists only in the git-ignored `FlightTrackerApp/.env`, and `eas.json` has no env block, so a cloud build doesn't get it; earlier TestFlight builds shipped an empty secret (`lib/watch.ts:266-270`). Without it `/watch`, `/watched` and `/alternatives` answer 404.
- **Steps:** set the secret as an EAS environment variable for the production profile (never commit it). After building, check that the built app carries it: install the build and confirm `/watched` requests from its user agent return 200 in the Cloud Run logs, and that saving a flight creates a watch row.
- **Done when:** build 13's requests to the secret-gated endpoints succeed.
- **Constraints:** never print the secret; never put it in the repo or `eas.json`.

## T10. Dev fixtures out of release builds
- **Why:** `lib/devFixtures.ts` is imported unconditionally by `lib/saved.tsx`, `lib/watch.ts` and `lib/alternatives.ts`, so it ships in release builds, contrary to its comments. `registerWatch` has no fixture guard: undoing the unsave of a fixture, or disowning one, registers it with the server, and disowning clears the dev trip id so a screenshot fixture with a real flight number (BA177) stops being recognised (§6.2, §6.12).
- **Steps:** add a fixture guard inside `registerWatch` (and any other network path); keep the fixture marker when a fixture is disowned; make the fixture module reachable only in `__DEV__` (dynamic import or a dev-only stub), and correct the comments.
- **Done when:** a release bundle contains no fixture data, and no fixture can reach `/watch` by any path (undo, disown, re-own).

## T11. Fix the storage schema fault
- **Why:** `normalizeRecord` pins every record at schema 11 while `SCHEMA_VERSION` is 15 (`lib/storage.ts:7, 600-603`), so the v12 and v13 upgrades run again and every non-empty saved list is rewritten on every read. Two overlapping read/write cycles can lose the newer save.
- **Steps:** make normalization stamp the current version and only write back when a record actually changed; keep the upgrades idempotent; correct the stale comment (it says 13) and the one in `lib/devFixtures.ts:215-217`. Add a node test for "reading an up-to-date list writes nothing".
- **Done when:** reading an up-to-date list performs no write, and older records still upgrade.

## T12. Header clock and greeting follow the trip's city (not started)
- **Why:** after landing, the header still showed the origin's time; the clock and greeting use the phone's zone today (`lib/flightstatus.tsx:100-104`, `app/(tabs)/index.tsx:269-285`).
- **Steps:** on Home, My Flights and Deck, follow the traveller's current owned trip, using the same idea of "where the traveller is" the Deck already uses: before the first departure, the origin's local time; from 30 minutes before the latest expected arrival, the destination's; after landing, that airport's time until the next leg departs. Always labelled with the city. With no trip in progress, the phone's time.
- **Done when:** the approved plan works on a dev build through a multi-leg fixture trip, with node tests for the switch points.
- **Constraints:** open question for Jay before building: should the greeting follow the city too?

## T13. "Time to leave" for a trip's first leg only, plus reminders for connecting legs (not started)
- **Why:** on the beta trip "time to leave" fired for connecting flights; every saved flight gets its own evening and time-to-leave pair today (`lib/reminders.ts:221-233`).
- **Steps:** plan first with Jay: which reminder a connecting leg gets instead (for example a "next flight" reminder at landing or a set time before its departure), then build. Existing reminders must be rescheduled when a flight joins or leaves a trip.
- **Done when:** a multi-leg trip schedules "time to leave" for the first leg only and the agreed reminder for each connecting leg, with node tests.

## T14. Local reminder wording to match the new push style
- **Why:** the local reminders still lead with the flight number ("BA177 tomorrow", then "Departs LHR at ..."), while server pushes now use route titles and personal one-line bodies (§6.1, §6.1a).
- **Steps:** propose the exact titles and bodies to Jay (evening before, time to leave, and T13's connecting-leg reminder), then implement exactly what he approves.
- **Done when:** local reminders read in the same voice as the pushes.

## T15. Open decisions where the code breaks a rule (Jay decides)
- **Why:** each is a conflict between one of Jay's rules and the code (§2.4). Nothing changes until Jay picks a side.
  - D1: pull-to-refresh exists on Home and My Flights; the rule says none anywhere.
  - D2: the page background is `#0a0a0a` in code; the design rule says #050505.
  - D3: saving a flight asks for notification permission, sometimes two prompts at once; the earlier decision was to ask only when setting a reminder.
  - D4: the layover warning stays after the first leg lands (the code does this deliberately); the handover said it must not.
  - D5: the disrupted card's "SCHEDULED DEPARTURE" shows the zone again; Jay had it removed.
  - D6: after a cancellation tap the route list opens sorted Fastest; the server asks for earliest.
- **Done when:** each has Jay's decision recorded, and any resulting change is a task of its own.

## T16. Update stale docs and copy
- **Why:** several documents and comments describe an older state.
- **Steps:**
  - `DEPLOY.md`: remove the claim that `BILLING_DAY` is still 7 (it is 14); rewrite the model provider section (the code defaults to Gemini; it describes Claude on Vertex); list the settings the code reads but the doc omits (`WATCH_SECRET`, both alert secrets, `EXPO_ACCESS_TOKEN`, `POLL_MAX_ADB`, `POLL_MAX_FR24`, `GMAIL_FIXTURE_TOKEN`); replace the FR24 cost section (it describes device polling); define `$PROJECT_NUMBER`; add the Cloud Scheduler jobs and the bucket lifecycle rules (`routelists/` 6 days, `boards/` 1 day).
  - `docs/connection-search.md`: the app half is built (it says Stage 3 is not started) and automatic searches exist behind the budget gate (it says searches are never automatic).
  - `pollstate.py:587`: the comment says the reset is on the 7th.
  - The 500-unit connection reserve premise (`pollstate.py:629-630`): one ten-hour flight now costs about 572 units, not 452. Jay decides the new figure.
  - Comments that still say the watchlist cap is 20, that the page is #050505, and DetentSheet's mode comment.
  - Website: the hero sub-line says two-minute checks happen "in the last ninety minutes" (`index.html:59`) and `support.html:37` says every 10 minutes in the last six hours; both become "from four hours before departure" after the traffic move (T3). The privacy page's route-list line (`privacy.html:55`) describes a route list as "the flights between two airports".
- **Done when:** each item is corrected, with website copy approved by Jay before it changes.
- **Constraints:** website copy follows the public-surface rules (no provider names, no Indian data).

## T17. The Indore to New York connection search UI problems
- **Why:** Jay saw several problems on that search and couldn't send screenshots.
- **Steps:** ask Jay what they were; reproduce in the dev client; fix.
- **Done when:** Jay confirms each one is fixed.

## T18. UI overhaul week (Mac)
- **Steps:** app icon; design system written from the website's rules; Swift / @expo/ui for cards and interactive parts; drawers, including where the alternatives drawer rests relative to the tab bar (ask Jay what "below the nav bar" means; the code puts it under the native tab bar today); borderless cards everywhere (collapsed leg rows still have a hairline); the connection row's long-press menu (action sheet) versus the card's glass panel; map polish (pole lines).
- **Done when:** Jay signs off the screens that go into the screenshots.

## T19. Screenshots, then the website
- **Steps:** follow the shot list (§6.14). Then swap the placeholder phones, make a new og.png (the current one shows the old design and old wording), bring the legal, support and 404 pages onto the new design, add Apple's badge at launch, and deploy only after the new server wording is live (T3).
- **Done when:** the live site serves the new design with real screenshots.
- **Constraints:** public-surface rules; the privacy policy says the site sets no cookies and loads nothing from other sites, so analytics must keep that true or the policy changes first.

## T20. Build 13 to TestFlight, then retire /parse and /chat
- **Steps:** after T9, T10 and T11 (and T12 to T14 if Jay wants them in), build with the production profile, check TestFlight, get every tester onto build 13, then remove `/parse` and `/chat` from the server once no build-12 requests appear in the logs.
- **Done when:** every tester runs build 13 and the old endpoints are gone.

## T21. Fix a tester's TestFlight install
- **Steps and details:** in the Project copy.

## T22. Launch blockers (in this order)
Account deletion in the app; secure `/watch` with the session instead of the shipped secret; move `watches.json` to a database; email import by forwarding instead of the Gmail restricted scope; crash reporting; the App Store listing, privacy labels, review notes and export compliance. Details in §16.

## T23. FR24 Stage 2
- **Steps:** measure the flight-events and live-positions endpoints (latency, credits) before deciding on a one-minute watch; fix the "Took off" push, which fires on the gate-out time (`notify.py:384, 566-577`); send gate-out and takeoff to the app.
- **Done when:** "Took off" fires on the actual takeoff, and the one-minute watch decision is made with measured costs.

## T24. Alternatives Stages 5 and 6, disruption notifications, "get what you're owed"
Stage 5: compact card for disrupted legs, the next undisrupted leg expands, carry over refresh and map toggle, re-point the deep link. Stage 6: search from the diversion airport. Then disruption notifications for alternatives, and the entitlements work (§16).

## T25. Credits follow-up
Anthropic startup credits (follow up early October); Google for Startups. Details in the Project copy.

## T26. Repo hygiene
Separate dev bundle id; `expo-dev-client` out of production dependencies (it is in `dependencies` today); merge `native-ios-tabs` into `master` (the default branch; there is no `main`).

## T27. Small fixes found in verification
- Gmail: the app's auto-add saves a leg the server has marked retired if the flight still operates (`lib/gmailPull.tsx:221-298`); respect the server's leg status.
- Booking cancelled: the notice marks pending legs only (`lib/saved.tsx:2637-2655`), and Home and My Flights use different wording (`app/(tabs)/index.tsx:1070-1076`, `app/(tabs)/flights.tsx:1469-1470`); agree one wording with Jay.
- A connection's wait prints "1h" on the row and "1h 00m" on the map bubble; pick one format.
- `/watched` sends the first 12 live flights in saved order, not by urgency; with more than 12 live flights the soonest may be left out.
- Set a Cloud Billing budget alert (the Billing Budgets API is not enabled on the project; enabling it is a settings change Jay approves).
