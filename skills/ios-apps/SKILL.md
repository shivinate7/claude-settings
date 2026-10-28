---
name: ios-apps
description: Use in any repo that ships an iPhone app, before you draw or brief an iPhone mockup, before you change its build, tests, CI or shipping, when the owner asks for a new iOS app, or before you fold or unfold an iPhone Duo simulator. Holds the one iOS standard every app follows, its mockup rules, and a starter that writes a new app at that standard.
---

Every iOS app of the owner works the same way: the same build, tests, phone install and TestFlight
path. This page is the standard. The look of each app stays its own: each app is its own product
(an owner ruling the iOS kit consultation records). Portability: every repo that ships an iOS app (home, degen, mailaudit,
ios-adblock). Not q_max, banchi or joyous, which ship none.

## The standard

| Area | Gold standard | Checked by |
| --- | --- | --- |
| Account IDs (team, phone, API key) | Once, in `~/.config/ios-ship/account.json` on the Mac. Never as `DEVELOPMENT_TEAM` in a project file, Makefile or workflow: `ios-ship` passes the team itself. A repo's `tools/ios-ship.json` may override a value (decision ios-ship-is-one-shared-tool, one shared ship tool), and the probe grades that `partial`. | `account ids` |
| Phone install and TestFlight | `make phone` first. `make testflight` when `make phone` fails. Both call `ios-ship` directly, with no script of the repo's own (decision ios-mac-install-first, Mac install first). | `ship path` |
| Same commands everywhere | `make phone`, `make testflight` and `make native-check` in every repo, and each does the same job. | `make targets` |
| Where app logic lives | A Swift package in the repo (`<App>Kit`). Its tests run in seconds with no simulator. A tiny app may skip it. | `kit package` |
| Project file | A short `project.yml`, made into the `.xcodeproj` by XcodeGen. Never commit the `.xcodeproj`. | `project file` |
| Swift language mode | 6.0 in the project, and `swift-tools-version` 6 or later in each package, with no language mode 5. | `swift 6` |
| Lowest iOS | iOS 26, unless a phone that must run the app is older. Write the reason in the repo either way. | by hand |
| Fast checks on every PR | CI on the pinned `macos-26` image (or a larger runner of it) runs the package tests and compiles every app on each pull request. It skips drafts and docs-only changes. | `ci runner`, `ci checks` |
| Slow tests (UI, full suite) | Once per batch, on the Mac, through `make native-check`. Its UI tests run through the shared `sim-test`, never in CI. | `slow tests` |
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
| `testflight` | `ios-ship testflight`: archive and upload | Mac |

## Folding the iPhone Duo simulator

`simctl` cannot fold a simulator, and this Xcode has no Simulator app. Use the `hinge` command
(artemnovichkov/hinge at commit `abd539d6`, at `~/.local/bin/hinge`, owner choice 2026-10-25). It
opens no window. Never drive Device Hub to fold.

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

## Mockups

This section is the one home of the iOS drawing rules. The designer, skill `design-explore` and skill
`design-review` point here. An iOS repo, for these rules, is a repo whose device list
(`python3 ~/.claude/lint/layout.py devices <repo root>`) holds both Duo poses. Hook `blind_brief.py` uses
the same test, and refuses a designer brief there that does not name this skill.

Before you draw, fetch the current Apple pages below and read the parts you use. Do not draw from memory,
and type no number that a page you read does not give. If a page does not load, say in your notes that
the read is unknown, and use no number from it. In your notes, cite each page you used, with the date you
read it.

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
- Type. The first family in each font-family is `-apple-system` or `system-ui`. Take each size from a
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
