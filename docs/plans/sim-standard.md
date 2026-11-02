# Prompt: one way to run iPhone simulators across all my repos

Make claude-settings the one home of iPhone simulator use on this Mac. Today each repo runs simulators its own way. Coordinators queue for one device by chat, and things keep breaking with no one seeing the cause. Below is everything found on 2026-11-02 by the gatekeeper session (local_9618917e-e65a-4dc7-84a1-af9ade87afef, "iPhone simulator resource management"). Read it, then plan the lanes yourself.

## My rulings (owner, in chat)

- 2026-10-25 20:26 CDT (Degen memory `duo-sim-fold`): I use only an iPhone Duo. The Duo simulator is the priority test device. A normal phone is second-tier.
- 2026-11-02 13:00 CST: one gatekeeper decides who gets the simulator. A holder that stops answering loses it after a set time, and the next session in line gets it. Priority goes to whoever's work is blocked most.
- 2026-11-02 13:05 CST: the shared simulator is the iPhone Duo, not an iPhone 17.
- 2026-11-02 13:17 CST: `sim-test` must point at a Duo, not an iPhone 18 Pro. Tests on both are best, but the Duo is the priority.
- 2026-11-02 13:17 CST: erase the shared Duo (done 13:18; it did not help, see below).
- 2026-11-02 13:49 CST: "this mac can only have one sim and it needs to be shared across the repos". No repo makes its own simulator (Degen included). The one simulator is the shared iPhone Duo AC2E94F9. The standard should drop "when a lane may make its own" and any per-lane device.
- 2026-11-02 13:51 CST: "Home can have an iphone 18 pro run only if the duo sim is turned off (ie only one phone sim at a time, across phones is still fine)". So the lease is one slot for the whole Mac: the shared Duo or the shared iPhone 18 Pro, never both booted. This replaces the guard's boot cap of 2 for phones. `sim-test`'s optional 18 Pro run must shut the Duo down first.
- 2026-11-02 14:23 CST: "If load is comfortable we can have two duo sims at once". A second shared Duo now exists: "iPhone Duo 2" 801F55F4-F666-4C6D-AB04-7DF77C953974 (iOS 27.1). So the lease has two Duo slots, and slot 2 opens only under a load bar. The gatekeeper set a provisional bar, unmeasured: a 5-minute load under 20 while slot 1 is in use. Measure the bar and set it in the standard. The 18 Pro may run only when no Duo is booted.
- 2026-11-02 13:26 CST: reinstall the iOS 27.1 runtime (done 13:31; it fixed the Duo, see below).

## Repos and who uses a simulator

| Repo | Coordinator session | Needs a simulator | For what | What a wait blocks |
| --- | --- | --- | --- | --- |
| home (Home side) | local_3f3e1fa4-2dd9-483d-9040-eec6a2e04fa9 | Yes, heavy | `sim-test` runs that fail then pass (18 Pro), design screenshots with `-fixture` (18 Pro and Duo), Duo fold checks. About 10 uses on 11-02 between 10:40 and 12:45, each 3 to 15 min | Design checks gating PRs 448, 473, 476, 485; duo-play slice B; duo-rooms items 66 and 71 |
| home (Apartment side) | local_52853462-4a1e-4cfe-baa7-4ce31929cf53 | Later | One Duo screen check for the lights lane, after I pick a layout | That lane's design review |
| degen | local_5dd6de3a-0edb-46f9-a592-669840edcd42 | Yes | h3-pill: proof runs and look shots on an iPhone, then a Duo fold. Batch runner: one `make native-check` per native batch. Each xcodebuild run takes 110 to 135 s (few runs measured) | The H3 native batch cannot ship to my phone |
| banchi | local_2af8dabf-62eb-4295-ac57-286984f44a38 | No | Web app (Vite + Playwright) | Nothing |
| ios-adblock | none active | Ships an iOS app (per `ios-apps`) | Unknown | Unknown |

Home and Apartment share the home repo, so they compete for the same devices.

## Devices on this Mac

- Shared iPhone Duo `AC2E94F9-0E44-4D9C-B27A-54DA45BC4698`, on iOS 27.1. Apple's own device type `iPhone-Duo`. Its profile requires iOS 27.1 or later, so a Duo on 27.0 is refused as "Incompatible device". Two screens: `LCD` (outer) and `LCD-1` (inner).
- Shared iPhone 18 Pro `8787FE1C-48CC-4213-9B5C-8605AFE7F9B3`, on iOS 27.0. `sim-test` boots it.
- Throwaway devices that lanes make: Degen's "h3pill iPhone 17" `2FCDF62B` (booted 11-02 13:01 for one run); a deleted "Degen Duo" `0828624E`.
- Runtimes: two iOS 27.0 images (24A5408d and 24A434), plus iOS 27.1 (24A94232), which was reinstalled on 11-02. Xcode 27.2 (27B52), installed 2026-10-31 12:09 CDT.

## Each repo runs the Duo differently

| Topic | Gold standard | home `records/duo-simulator.md` | degen memory `duo-sim-fold` | claude-settings `skills/ios-apps/SKILL.md` |
| --- | --- | --- | --- | --- |
| Which Duo | One rule for all | Shared AC2E94F9 | Each lane makes its own Duo, then deletes it; never touch AC2E94F9 | Not stated |
| hinge version | One pinned version | 0.3.0 `afb8f0bd`; the link at `~/.local/bin/hinge` points here (upgraded 11-01) | 0.2.0 `abd539d6` | 0.2.0 `abd539d6` |
| Screenshot names | One naming | `--display=1` / `--display=3`, or `hinge screenshot` | `--display=LCD` / `LCD-1` | `--display=LCD` / `LCD-1` |
| Lock | One tracked tool | None; asks the gatekeeper | `~/.claude/locks/ios-simulator.lock`, tracked nowhere | None |
| Confirm timeouts | One rule | Usually a false alarm: read `hinge get`; 21 of 53 calls timed out | Read `posture` | Read `posture` |
| After a boot | One rule | The pose resets to closed and portrait: set it first | Open, then close again, if the outer screen is stale | Same as Degen |
| Erase | One rule | Never erase without the owner (it wipes the Home Assistant sign-in) | n/a | n/a |

Home's record also hands off two skill edits that never landed: "a new iOS runtime can break `hinge`; delete `~/.cache/hinge` first", and "a confirm timeout usually landed".

## What broke

1. **The Duo on iOS 27.1 fails on this Mac, whatever the device.** Since Xcode 27.2: 34 Duo boots gave 8 boot-check fails, then 3 gave 2; the 18 Pro had 0 fails in 17 boots. Since 11-02 12:05 CST the Duo boots to "Data Migration Failed" with a black screen. On 11-02 the gatekeeper erased AC2E94F9: same fault. A brand-new Duo on 27.1: same fault. Each lane blamed its own device.
2. **Crash storms.** About 25 PosterBoard and 25 SpringBoard crash reports in `~/Library/Logs/DiagnosticReports`. By day: 10-27: 23; 10-28: 3; 10-29: 2; 10-30: 1; 11-01: 20; 11-02: 1. The 11-02 PosterBoard crash (EXC_BREAKPOINT) came from the gatekeeper's test Duo boot at 19:20 UTC.
3. **The boot check reports false fails on the Duo.** `hooks/sim_boot_record.py` (decision `sim-boot-is-verified`) takes a plain `simctl io <udid> screenshot`. On the two-screen Duo that fails with "Invalid argument". The check reboots the device, which also resets its fold. Lanes learned to ignore the check, and it hid fault 1.
4. **No exclusive use.** The guard caps booted devices at 2 and refuses a twin of an idle device. The sweep shuts devices down after 1 hour idle (`sweep-shuts-down-idle-simulators`). Nothing gives one session sole use of a device. On 11-02:
   - Home's 2-minute 18 Pro run was refused by the cap while the gatekeeper's Duo and Degen's iPhone 17 held both slots.
   - Two Home lanes overwrote each other's app install on the Duo before taking screenshots.
5. **`sim-test` reuses "the first booted iPhone".** It can pick another lane's throwaway phone, such as Degen's iPhone 17, instead of the shared device.
6. **A gatekeeper session is not a durable home.** It sleeps, dies and costs context. The queue order and the timeout must live in a record and a tool, not in one chat session.
7. **Disk.** Each Duo adds about 14 GB. A 10 GB backup of the Duo from 11-01 sits at `~/Library/Developer/CoreSimulator/poster-backup-AC2E94F9-20261101/`.

## Compile without a simulator (data from the Degen batch runner, 11-02)

- Degen's `make native-check` runs `xcodebuild build-for-testing -destination 'generic/platform=iOS Simulator'`. That compiles the app and its UI-test bundle with no simulator. Logic tests (about 7,570 in the DegenKit package) run on the Mac with `swift test`. 371 UI tests are compiled but run only per lane, and only those a change touches.
- This is already the standard: the `ios-apps` Makefile template's `app-build` does the same. Home's Makefile also builds against the generic target, but with `xcodebuild build`, so it does not compile its UI-test bundle.
- Value of the UI run: on 11-02 at 13:21 CST, a Degen UI test on the simulator caught a bug (the Feed popover did not close on "Top") that the logic tests and the build missed. So the compile step does not replace the simulator run; it keeps the slot free for UI runs only.
- The standard should say: prove the build with the generic target, never by booting the slot; use the slot only for UI tests a change touches, and for screenshots; batch a lane's runs into one visit. XCUITest taps do nothing on the folded Duo, so folded cases are untested.

## Work already done (do not redo blind)

- Local branch `claude/sim-lease-592a4d` in claude-settings (head d1fda8f3), made by a lane I stopped at 13:26 CST (session local_7057455f-ae35-46ee-85a5-bb71a695b230). It is not pushed. Branch `test-ci-scope-sim-lease` (commit a326b9fc, the CI-scope test) is on origin. Its commits:
  - commit b25cc1d0 adds `bin/sim-lease`: an exclusive lease on the shared Duo, which expires 20 min after the last renew unless a recorded job pid is alive; a queue the gatekeeper ranks; state in `~/.claude/state/sim-lease.json`; checked on each call, with no timer.
  - commit 165dfede holds decision record `sim-lease`, ruling 2: `sim-test` runs on the Duo first, with an optional 18 Pro run.
  - It has no PR and no finished review. Read it, then reuse it or replace it.
- iOS 27.1 runtime: deleted, then downloaded again with `xcodebuild -downloadPlatform iOS -buildVersion 27.1` (7.85 GB, new image C77A48A3). The erased AC2E94F9 then booted to its home screen, with no "Data Migration Failed" and no new crash. So the fault was a damaged runtime image, not the device and not Xcode. The standard should say: when a fresh device of a type fails too, reinstall that runtime; do not erase devices.
- Later the same day (13:40–13:45 CST) the Duo failed again: "Data Migration Failed", and even a named-display screenshot failed for about 2 minutes while SpringBoard ran. The 5-minute load was about 130 to 173, mostly swift-frontend builds. Clean boots at 13:31–13:36 ran under lighter load. Working theory, unmeasured: the Duo's first-boot step times out under load. Interim rule, given to the coordinators: boot the Duo only when the 5-minute load is under 30. Measure it, then put a load bar in the standard or in the boot check. First data point: at 14:23 CST a Duo boot was clean at a 5-minute load of 32 (no "Data Migration Failed"; the named-display screenshot worked at once). The gatekeeper's interim bar is under 40.

## What I want

1. **One simulator standard**, in one home in claude-settings, covering:
   - which devices are shared, by UDID, and when a lane may make its own;
   - how to boot one and prove it is up, naming a screen;
   - one pinned `hinge` version and how to use it;
   - screenshot screen names;
   - priority order: a merge gate first, then a design gate, then anything else;
   - the timeout;
   - clean-up on exit, including the build installed on a shared device;
   - erase rules;
   - what to do when the runtime breaks.

   Then each repo replaces its own copy with a pointer: home's `records/duo-simulator.md`, Degen's memory note, and the lines in each repo's CLAUDE.md. Message each coordinator above to make that change in its own repo.
2. **Exclusive use with a timeout and a queue**, with no gatekeeper session needed, and `sim-test` on the Duo first (my 13:17 ruling).
3. **A boot check that works on the Duo**, plus a message that says "runtime fault, not this device" when a fresh device fails too.
4. **A guard rule only if you judge it worth it**, for boots, `hinge` and simulator MCP launches on a gated device by a session without the lease. The incident is item 4 above.

Ask me before any erase or delete of a shared device, and before any runtime or Xcode change.
