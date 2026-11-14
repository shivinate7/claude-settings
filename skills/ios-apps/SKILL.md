---
name: ios-apps
description: Use in any repo that ships an iPhone app, before you draw or brief an iPhone mockup, before you change its build, tests, CI or shipping, when the owner asks for a new iOS app, before you fold or unfold an iPhone Duo simulator, or before an Xcode build, swift test, or a simulator lease or boot. Holds the one iOS standard every app follows, its mockup rules, and a starter that writes a new app at that standard.
---

Every iOS app of the owner works the same way: the same build, tests, phone install and TestFlight
path. This page is the standard. The look of each app stays its own: each app is its own product
(an owner ruling the iOS kit consultation records). Portability: every repo that ships an iOS app (home, degen, mailaudit,
ios-adblock). Not q_max, banchi or joyous, which ship none.

## The standard

| Area | Gold standard | Checked by |
| --- | --- | --- |
| Account IDs (team, phone, API key) | Once, in `~/.config/ios-ship/account.json` on the Mac. Never as `DEVELOPMENT_TEAM` in a project file, Makefile or workflow: `ios-ship` passes the team itself. A repo's `tools/ios-ship.json` may override a value (decision ios-ship-is-one-shared-tool, one shared ship tool), and the probe grades that `partial`. | `account ids` |
| Phone install and TestFlight | `make phone` first. `make testflight` when `make phone` fails. Both call `ios-ship` directly, with no script of the repo's own (decision ios-mac-install-first, how a build reaches the phone). | `ship path` |
| Same commands everywhere | `make phone`, `make testflight` and `make native-check` in every repo, and each does the same job. | `make targets` |
| Where app logic lives | A Swift package in the repo (`<App>Kit`). Its tests run in seconds with no simulator. A tiny app may skip it. | `kit package` |
| Project file | A short `project.yml`, made into the `.xcodeproj` by XcodeGen. Never commit the `.xcodeproj`. | `project file` |
| Swift language mode | 6.0 in the project, and `swift-tools-version` 6 or later in each package, with no language mode 5. | `swift 6` |
| Lowest iOS | iOS 26, unless a phone that must run the app is older. Write the reason in the repo either way. | by hand |
| Fast checks on every PR | CI pins the macOS image by the SDK the apps need. Today that is `macos-26` (or a larger runner of it), which holds the iOS 26.5 SDK. It runs the package tests and compiles every app on each pull request. It skips drafts and docs-only changes. An app that needs a newer SDK than any image holds adds `tools/ios-ci-exemption.json`, `{"sdk": "...", "reason": "..."}` (both non-empty strings, tracked in git), and compiles on the Mac through `make native-check`. The form waives the app compile only: the package tests and a pull-request workflow stay required on every PR, and `ci runner` stays a gap with no macOS workflow. The probe grades `ci checks` `pass` with `exempt: <sdk>` when it used the waiver. A broken, untracked or unreadable form is a gap. | `ci runner`, `ci checks` |
| Slow tests (UI, full suite) | Once per batch, on the Mac, through `make native-check`. Its UI tests run through the shared `sim-test`, never in CI. `sim-test` passes `-collect-test-diagnostics never`, so a failed test starts no diagnose. | `slow tests`, `test diagnostics` |
| Colours and spacing | One `tokens/tokens.json` per app. The Swift is generated from it, never typed by hand, and CI checks that it is current. | by hand |
| Test style | Swift Testing for new tests, XCTest for UI tests. Old tests stay as they are. | by hand |

"Checked by" names the item of the `ios` probe: `python3 lint/compliance_probes.py ios <repo>` from
this repo (the `compliance-check` skill runs it). A row checked by hand is read in a repo visit.

## The make targets

| Target | Does | Runs where |
| --- | --- | --- |
| `tokens` | writes the Kit's `Tokens.swift` from `tokens/tokens.json` | Mac |
| `tokens-check` | fails when `Tokens.swift` is stale | CI and Mac |
| `kit-test` | `swift test` on the Kit package | CI and Mac |
| `app-build` | XcodeGen, then a compile of every app for the iOS simulator | CI and Mac |
| `ui-test` | the UI tests on the shared simulator, through `sim-test` (roadmap step c89, one shared simulator tool; it fails until c89 lands on main) | Mac |
| `native-check` | all four checks above, once per batch | Mac |
| `phone` | `ios-ship install`: a Release build on the phone | Mac |
| `testflight` | `ios-ship testflight`: archive and upload; `--export-only [--method debugging\|release-testing]` exports an .ipa | Mac |

## Folding the iPhone Duo simulator

`simctl` cannot fold a simulator, and this Xcode has no Simulator app. Fold with
`bin/duo-fold <udid> <folded|open>`. It folds with `hinge` (artemnovichkov/hinge, owner choice
2026-10-25), reads the angle back, and refuses unless the angle is within 0.5 of 0 (folded) or 180
(open). Exit 0 passes. Exit 1 is a refusal, with a `duo-fold:` line on stderr. Exit 64 means wrong
arguments. A hinge move that exits non-zero is noted on stderr, and the angle is still read. No
retry. The tool runs only on an arm64 Mac; on any other machine it exits 1 before any hinge call.
With `HINGE` unset, it fetches hinge v0.3.0 at its pinned commit,
`afb8f0bd277cb12187f0844a79542cbac35e7385`. The tool's pin is the one to use.
`~/.local/bin/hinge` (commit `abd539d6`) is for hand use. It opens no window. Never drive Device
Hub to fold.

- `hinge -d <udid> open|close|half|<degrees>|get|posture`. Run it outside the sandbox. When
  `-t 6` times out, read `posture`: the angle may be set already.
- Name the screen in each screenshot: `simctl io <udid> screenshot --display=LCD` for the outer
  screen, `--display=LCD-1` for the inner one. The default screen changes between runs.
- After the first `close`, the outer screen may not update. Open and close again, and check an
  outer screenshot shows the app before tests run.
- UI tests anchor taps and drags on the app's window, not on `app`. With the phone open, `app`
  coordinates land on the dark outer screen.
- `hinge` uses private Apple APIs, so an Xcode update can break it. Then the owner folds by hand:
  Xcode > Open Developer Tool > Device Hub has Closed, Partial and Open buttons.

## Sharing the Mac

Every session on this Mac shares its builds, its simulators and its disk. Each rule here holds in every repo on the Mac. Degen and home each copied these rules. This section is their one home.

- **One build at a time** (the one-build rule, which widens degen `one-xcode-build-at-a-time` to every session on the Mac, at the coordinator's request on 2026-11-03). Each session on this Mac runs at most one Xcode build or test at a time, across all its agents. An Xcode build, `swift test` and `make native-check` each count. Load average does not limit a build (owner, 2026-11-02 21:28 CST). The owner then dropped the CPU and memory checks (owner, 2026-11-02 21:54 and 21:55 CST). A simulator crash means the Mac is overloaded: slow down and queue, and never retry at once (owner, 2026-10-27 19:33 CDT).
- **Leased simulators** (the lease rule, degen `shared-sim-lease`). No repo creates a simulator. Each session leases a phone simulator through `bin/sim-lease`, the one home of the queue and the lease for all sessions on the Mac (owner, 2026-11-02 13:49 CST; decision `sim-lease-tool`). The Mac sim gatekeeper session reads `sim-lease status` and need not stay awake.
- **Phone simulators.** Claude may use three (home's iPhone simulators rule: owner, 2026-10-11; widened 2026-10-14, 2026-10-26 and 2026-10-29). Optimize every app for the Duo and the 18 Pro, Duo first (owner, 2026-10-26).
  - Slot 1, Duo 1: `3553660D-315C-4B9C-8614-039D7A5B637E`, iOS 27.1 (owner, 2026-10-11). The UDID is from owner, 2026-11-02 14:47 CST. Fold it with `bin/duo-fold`, as above.
  - Slot 2, Duo 2: `801F55F4-F666-4C6D-AB04-7DF77C953974`.
  - iPhone 18 Pro: `86F9268A-A905-4B82-9BC0-D7EBB682D341`, iOS 27.0, which replaced the deleted 8787FE1C (owner, 2026-11-07 19:16 CST).
- **Boot bars** (degen `shared-sim-lease`). One phone simulator boots at a time (owner, 2026-11-02 13:51 CST). The one exception is the two Duos, which may run together when the load allows (owner, 2026-11-02 14:23 CST), one per slot (Mac sim gatekeeper text). The next in line takes the first slot to become free. A phone simulator boots only while the 5-minute load is under 100. Slot 2 boots only while the 5-minute load is under 60 and slot 1 is in use (owner, 2026-11-02 14:28 CST). Boots go one at a time, and each needs a 1-minute load under 60 (Mac sim gatekeeper, 2026-11-02 14:34 CST). The 18 Pro never runs beside a Duo (owner, 2026-11-02 13:51 CST). `bin/sim-test`, the one simulator test script, boots it only with `--device pro`, only when no iPhone is booted, and only after `sim-lease take --device pro` grants it. `bin/sim-lease` enforces the load bars and the slot rules on each grant.
- **Holder's duties.** A session that holds a phone simulator takes its lease with `bin/sim-lease take` and frees it with `bin/sim-lease give`. Those two calls are the start and end notices, and the queue orders the places (decision `sim-lease-tool`). `--pid` names a process that lives for the whole hold. A Bash tool call's own shell (`$$`) dies when the call ends, so its lease is reaped at the next call. A direct caller sets `--wait` under the tool's timeout and checks with `sim-lease status` that its lease is still listed. It shuts down each simulator it boots, after its check. It leaves each Duo as it found it, with no app running, except the PosterBoard store sim-test deletes. `bin/sim-test` itself deletes the PosterBoard store of the device it is about to boot; a holder deletes and erases nothing else. If a boot fails with "Data Migration Failed" while the 5-minute load is under 100, it shuts the device down and sends the Mac sim gatekeeper the load (owner, 2026-11-02 14:28 CST). A session whose turn is busy passes its place to the next session (owner, 2026-11-02 14:31 CST). It starts `take` only when it is ready to boot, and gives the lease as soon as it cannot use it (decision `sim-lease-tool`).
- **Boot path.** Boot a simulator through `bin/sim-test`. It runs on the Duo by default (`--device duo`; owner, 2026-11-02 13:17 and 15:03 CST) and on the 18 Pro with `--device pro`. It reuses the booted device of its role. With a phone of the other kind booted, it boots nothing and exits 1, since one phone kind runs at a time. With no iPhone booted, it boots the role's device, unless two or more simulators are already booted. Then it boots nothing and exits. It takes one lock for the whole Mac, so a second run waits. On its own boot it also takes the role's lease from `bin/sim-lease` and boots the UDID `take --udid` prints. That tool waits for the queue and the load bars, and reads the load itself (`sysctl -n vm.loadavg`). Sim-test reads no load bar. The reuse path holds its slot's lease with `take --for-udid` (no load bars). On its own boot it first deletes the device's PosterBoard snapshot store, which grows without bound (owner, 2026-11-13 00:51 CST; decision `sim-test-is-the-one-boot-path`, ruling 10). On its own boot it also tries to disable the Siri, intelligence, Mail and Spotlight daemons that crash on every iOS 27.1 boot; the list lives in `bin/sim-noise-services`. It runs the tests, then shuts down what it booted and gives the lease back. `--hold [--for S] [-- CMD]` keeps that device for S seconds (default 300, max 900) under the same lock, for a design shot, then cleans up the same way (decision `sim-test-is-the-one-boot-path`, rulings 8, 9 and 10). The guard rule `simulator-boot-bypass` refuses a raw boot. Two boot paths still skip the lock: an `xcodebuild -destination` that names a shut-down device, and the simulator MCP tool's `launch` (decision `sim-test-is-the-one-boot-path`, ruling 5).
- **Use sparingly.** Test in code first. Boot a simulator only for the one short Mac check per batch, or for a screen check of a large finished piece of work. A compile check that opens no simulator is always allowed: `xcodebuild build-for-testing -destination 'generic/platform=iOS Simulator'`. Phone installs on the real device stay allowed.
- **Disk floor** (home's disk-floor ruling, owner, 2026-10-20 21:45 CDT). Keep at least 15 GB free on the Mac (`df -h /System/Volumes/Data`). Check it before each build. Delete each lane's derived data and worktrees when its build or merge is done.
- **Checks.** `bin/sim-lease` enforces the boot bars and the slot rules for a boot through `bin/sim-test`; `lint/test_sim_lease.py` tests it. No check enforces the one-build rule, and none enforces the bars on the two boot paths that skip `sim-test`. The 15 GB floor has no check. Guard rule `simulator-boot-cap` refuses a boot past the cap of two booted devices. Guard rule `simulator-boot-twin` refuses a boot that duplicates an idle device.

## Mockups

This section is the one home of the iOS drawing rules. The designer, skill `design-explore` and skill
`design-review` point here. An iOS repo, for these rules, is a repo whose device list
(`python3 ~/.claude/lint/layout.py devices <repo root>`) holds both Duo poses. Hook `blind_brief.py` uses
the same test, and refuses a designer brief there that does not name this skill.

Before you draw, fetch the current Apple pages below and read the parts you use. Do not draw from memory,
and type no number that a page you read does not give. If a page does not load, say in your notes that
the read is unknown, and use no number from it. In your notes, cite each page you used, with the date you
read it.

Each page below is a script shell with no text. Its text is at the same path under
`https://developer.apple.com/tutorials/data/`, with `.json` added, in the field `primaryContentSections`.
For example, `https://developer.apple.com/tutorials/data/design/human-interface-guidelines/buttons.json`.

Pages read 2026-10-28 (each answered 200):

| Page | What it gives a mockup |
| --- | --- |
| https://developer.apple.com/design/human-interface-guidelines/layout | Respect the system safe areas, margins and guides. The safe area is the part of the screen that the status bar, a toolbar, a tab bar or the Dynamic Island does not cover. Lay out by size class (compact or regular width), not by device type. |
| https://developer.apple.com/design/human-interface-guidelines/typography | SF Pro is the iOS system font. Use the built-in text styles: they give Dynamic Type. The page has the table of Dynamic Type sizes; the body style is 17 pt at the default size. |
| https://developer.apple.com/design/human-interface-guidelines/accessibility | On iOS, the default control size is 44x44 pt and the minimum is 28x28 pt. The default text size is 17 pt and the minimum is 11 pt. Let people make text larger, to at least 200 percent. |
| https://developer.apple.com/design/human-interface-guidelines/buttons | A button needs a hit region of at least 44x44 pt. |
| https://developer.apple.com/design/human-interface-guidelines/sheets | A sheet is for a simple task. In a sheet, Cancel goes on the leading edge of the top toolbar, and Done on the trailing edge. |
| https://developer.apple.com/design/human-interface-guidelines/lists-and-tables | Show text in a list or a table. |
| https://developer.apple.com/design/human-interface-guidelines/tab-bars | A tab bar is for navigation, not for actions. On iOS it floats above the content at the bottom of the screen. |
| https://developer.apple.com/design/human-interface-guidelines/toolbars | On iOS, a large title changes to a standard title when people scroll. The old navigation-bars page is gone (404); this page holds its guidance. |
| https://developer.apple.com/documentation/swiftui/navigationstack, https://developer.apple.com/documentation/swiftui/tabview, https://developer.apple.com/documentation/swiftui/list | The SwiftUI views that the mockup's navigation stack, tab bar and lists become. |

Draw with native controls and native proportions:

- Controls. Draw what SwiftUI gives: a navigation stack with a large title, lists, sheets, and a tab bar
  for the sections. Draw no control that iOS does not have, such as a hover state, a web page footer or
  a row of web buttons.
- Type. The app chrome's font-family starts with `-apple-system` or `system-ui`. Take each size from a
  Dynamic Type text style on the typography page, at the default size.
- Safe areas. Pad each frame with `env(safe-area-inset-top)` and the other insets, and keep content and
  controls out of the status bar and the home indicator areas.
- Targets. Make each tap target at least 44x44 pt.

Draw the Duo first. Draw the folded pose, then the unfolded pose. Each pose is its own layout, by the
layout page's size-class rule: the unfolded pose uses its width, for example a list beside its detail. It
is never the folded layout made wider. Put each pose in its own frame, with
`data-device="iphone-duo-folded"` or `data-device="iphone-duo-unfolded"`. Draw the regular iPhone only
when the brief or the owner asks. No Apple page gives a Duo size: take each size from `layout.py devices`,
and when it says `not written`, draw at the brief's size and say so in your notes.

Before you report, run `python3 ~/.claude/lint/check_ios_mockup.py <mockup>` on each mockup. Exit 0 is
clean. It checks only that a part is there: the system font first, a safe-area inset, and both Duo frames,
folded first. It does not judge the look. The design reviewer gives each screen a verdict, `native` or
`web-like` (skill `design-review`).

## Test shapes

Pick the shape by what the test proves. Extends decision `test-practices` (P1: assert the outcome the person meets; P5: no fixed sleep, no clock). Where each kind runs follows the "Fast checks" and "Slow tests" rows above and decision `swift-tests-at-milestones`.

| What the test proves | Shape | Runs where |
| --- | --- | --- |
| A rule (a sum, a parse, a sort, a state change) | Swift Testing in the Kit, through `swift test`. No view, no simulator. | `make kit-test`, CI and Mac |
| A screen looks right | Render test: build the view, render it to an image at each size and theme the app ships in, and check the image. It never launches the app. | `make kit-test`, CI and Mac |
| A press, a gesture or a move between screens works | XCUITest smoke: one or two cases per screen. | `make ui-test`, Mac, once per batch |

- Never test a rule through the UI, and never launch the app to see a layout. Each costs a simulator for what a faster shape proves.
- A render test names every size the app ships in. A size left out is untested.
- Every UI tap goes through one helper in the UI test target. The helper taps at the centre of the drawn shape's frame, never at a guessed offset. On the Duo, the helper anchors on the window, as in "Folding the iPhone Duo simulator".
- A UI test waits on state: `waitForExistence`, or a predicate on an element's value. It never sleeps and never reads a clock (P5).
- A bug a press or gesture lets through gets a smoke case on its screen. A bug a rule lets through gets a Kit test.

## A new app

Run the starter from this skill's folder. It writes into an empty folder, or into a repo that has
none of its paths. It never overwrites a file and never runs git.

```
python3 scripts/new_app.py <dest> --name Tally --bundle-id dev.example.tally --repo-url https://github.com/<owner>/<repo>.git
```

It writes `project.yml`, the Makefile above and the `TallyKit` package with one Swift Testing test.
It also writes one UI test, `tokens/tokens.json` with its generator and the generated `Tokens.swift`,
the CI workflow and the `tools/ios-ship.json` entry. Then:

1. Run `make native-check` on the Mac.
2. Add a 1024 px icon to `native/Tally/Assets.xcassets/AppIcon.appiconset`. App Store Connect
   refuses an app with no icon.
3. Register the bundle ID on the Apple team, then run `make phone`.

`tests/test_new_app.py` proves the tree the starter writes. No test here compiles it: the first
`make native-check` on the Mac does.

## What this page does not cover

- When to install on the phone after a merge. It waits on the owner.
- A shared Swift package across the apps. None exists.
