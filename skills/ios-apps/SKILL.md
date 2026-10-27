---
name: ios-apps
description: Use in any repo that ships an iPhone app, before you change its build, tests, CI or shipping, or when the owner asks for a new iOS app. Holds the one iOS standard every app follows, and a starter that writes a new app at that standard.
---

Every iOS app of the owner works the same way: the same build, tests, phone install and TestFlight
path. This page is the standard. The look of each app stays its own (owner, 2026-10-20: each app is
its own product). Portability: every repo that ships an iOS app (home-app, degen, mailaudit,
ios-adblock). Not q_max, banchi or joyous, which ship none.

## The standard

| Area | Gold standard | Checked by |
| --- | --- | --- |
| Account IDs (team, phone, API key) | Once, in `~/.config/ios-ship/account.json` on the Mac. Never in a repo: not in `tools/ios-ship.json`, not as `DEVELOPMENT_TEAM` in a project file (decision ios-ship-is-one-shared-tool, one shared ship tool). | `account ids` |
| Phone install and TestFlight | `make phone` first. `make testflight` when `make phone` fails. Both call `ios-ship` directly, with no script of the repo's own (decision ios-mac-install-first, Mac install first). | `ship path` |
| Same commands everywhere | `make phone`, `make testflight` and `make native-check` in every repo, and each does the same job. | `make targets` |
| Where app logic lives | A Swift package in the repo (`<App>Kit`). Its tests run in seconds with no simulator. A tiny app may skip it. | `kit package` |
| Project file | A short `project.yml`, made into the `.xcodeproj` by XcodeGen. Never commit the `.xcodeproj`. | `project file` |
| Swift language mode | 6.0 in the project, and `swift-tools-version` 6 or later in each package, with no language mode 5. | `swift 6` |
| Lowest iOS | iOS 26, unless a phone that must run the app is older. Write the reason in the repo either way. | by hand |
| Fast checks on every PR | CI on the pinned `macos-26` image runs the package tests and compiles every app. It skips drafts and docs-only changes. | `ci runner`, `ci checks` |
| Slow tests (UI, full suite) | Once per batch, on the Mac, through `make native-check`. Its UI tests run through the shared `sim-test`, never in CI on each PR. | `slow tests` |
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
| `ui-test` | the UI tests on the shared simulator, through `sim-test` | Mac |
| `native-check` | all four checks above, once per batch | Mac |
| `phone` | `ios-ship install`: a Release build on the phone | Mac |
| `testflight` | `ios-ship testflight`: archive and upload | Mac |

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
