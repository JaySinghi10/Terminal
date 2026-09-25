# Swift rebuild plan

Decided 25 September 2026. This file is the plan for rebuilding the iPhone app natively in Swift. Read it together with docs/HANDOVER.md (how Terminal works and its rules) and docs/TASKS.md (open tasks).

## The decision
- The iPhone app is being rebuilt as a native Swift app (SwiftUI, iOS 26 minimum), for quality: real Apple feel everywhere, Live Activities, Dynamic Island, widgets, and later iPad, Mac and Apple Watch.
- The React Native app in android/ is frozen. No more work on it. It becomes the starting point for a future Android app.
- The server in server/ stays as it is. The Swift app uses the same endpoints the React Native app uses today.
- Target: about 1 to 1.5 weeks to reach where the React Native app is today. Jay is putting in the hours.

## Folder layout
- apple/: the Swift app (to be created in Xcode on the Mac). One Xcode project; iPad, Mac, Watch, widgets and Live Activities are added later as targets inside it, sharing the same code.
- android/: the frozen React Native app, base for Android later.
- server/: the Python backend on Cloud Run.
- website/: the marketing site on Vercel.
- shared/: to be created when the Swift app needs data both apps use (airports, dining, terminals).
- tools/: the dining, terminals and indoor data pipelines (move to shared/ later).
- docs/: handover, tasks, specs, this plan.

## How we build: one screen at a time
Each screen is finished completely, including its server side, before the next one starts. If something turns out to be missing later, we go back to it; we don't leave screens half done on purpose.

For every screen, in this order:
1. **Inventory.** Read the React Native version in android/ and list everything the screen shows and does, every server endpoint it calls, every piece of phone-side logic it needs, and every test that covers that logic. Jay approves the list.
2. **Rules first.** Port the phone-side logic to Swift with its tests, and make the tests pass. The node tools in android/tools/ describe some rules exactly: departure, arrival, pending legs, the connections client, airports and the map loader. Catchability, layover warning bands, the refresh window, reminders and storage have no tests; for those, the inventory step writes the rules down from the React Native code first, and the Swift app gets tests for them.
3. **Build the screen** in SwiftUI with the design system.
4. **Check it on Jay's phone** against the inventory. Fix until Jay approves.
5. **Mark it done** in the checklist below and commit.

## Proposed order (Jay can change it)
- [ ] 0. Foundation: the Xcode project in apple/, design system (colours, fonts, spacing, corners), the server client, local storage for saved flights, device id, push registration. Built as part of screen 1.
- [ ] 1. Welcome, guest and sign-in
- [ ] 2. Home (search field, result card, watchlist)
- [ ] 3. Flight card (every phase: before departure, delay count, in the air, landed, belt, stale, cancelled, diverted)
- [ ] 4. My Flights (trips, layovers and warnings, disrupted cards, the alternatives drawer)
- [ ] 5. Notifications and reminders (tap opens the right flight; reminders with the first-leg rule)
- [ ] 6. Search (route search, results sheet, catchability, map, connection search, typed questions)
- [ ] 7. Deck (airport screen: dining by security side, terminal schematics, layover time)
- [ ] 8. Profile (settings, sign-out, email import, dev-only tools)
- [ ] 9. TestFlight: the Swift app replaces the React Native build
- [ ] 10. After parity: Live Activities, widgets, then the UI overhaul screen by screen

## Rules for the Swift app
- Every product rule in docs/HANDOVER.md §2.2 applies: no false or estimated-as-fact data, Flightradar24 is the only authority for "landed", never send the user to the airline, and so on.
- The data rules for times, belts, gates and status come from the data accuracy investigation (docs/TASKS.md). The Swift app follows the corrected rules, not the React Native app's mistakes.
- Secrets never go into git. The watch secret is supplied through a git-ignored config file, and the built app must be checked to actually carry it (earlier TestFlight builds shipped it empty).
- Bundle id com.terminalaero and a new App Store Connect record, "Terminal Aero". The home screen name is "Terminal". Nothing carries over from the React Native app's TestFlight builds or App Store record.
- No third-party packages without Jay's approval, with their cost and licence stated first.
- Builds come from Xcode (no EAS needed for the Swift app).

## Decisions to make before the screen that needs them
- **Sign-in screen:** Apple may require Sign in with Apple when an app offers Google sign-in. Check the current App Store guideline first. Also decide whether sign-in stays Google-based once email import moves to a forwarding address.
- **Background colour:** decided 25 September: #050505, the design rule. (The React Native app used #0a0a0a.)
- **Refresh:** the rule says no pull-to-refresh, but the React Native app has it on Home and My Flights. Decide for the Swift app.
- **Notification permission:** when to ask (the React Native app asks when saving, sometimes twice).
- **Map:** Apple Maps, the native version of MapLibre, or Mapbox (indoor maps later).
- **Testers' saved flights:** settled by the new bundle id: the Swift app is a separate app and cannot read the React Native app's storage, so it starts empty and testers re-add their flights.
- **How Jay reviews:** approve every code diff (today's rule), or try each finished screen on the phone and give feedback. Faster reviews make the one-week target realistic.
- **The other code-versus-rule conflicts** listed in docs/HANDOVER.md (D4 to D6).
