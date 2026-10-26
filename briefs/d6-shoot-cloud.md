# d6: one screenshot command, shared from claude-settings

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main bf084df.
Base branch: next-batch branch named by the build advisor (or main bf084df); never rebase onto main after review.

## Rulings

- Oct 17: build the shared script in claude-settings. Adding it to each child repo, and fixing
  banchi's 1280x900 viewport, is Roll out (deferred). Do not touch other repos.
- Oct 20 (o11): one script, installed like the hooks; each repo keeps only a config (URL, sizes,
  themes, simulator). The script is the check; a browser is for exploring.
- Oct 26: cloud sessions ship Chromium and Playwright, so the script needs no MCP (d8 folds in).

## Task

1. Add `shoot` to bin/, the home of the installed shared tools (verdict, ios-ship). The ruling's
   text says scripts/shoot; claude-settings has no scripts/ folder, so bin/ is the same intent.
   Say this deviation in the PR. Add a .cmd shim only if bin's existing tests require one.
2. `shoot [--config F]` reads a per-repo config (default `.claude/shoot.json`): base URL, routes,
   sizes (widths, default 1440 and 820, and 390), themes (light, dark via prefers-color-scheme),
   optional iOS simulator UDID. It writes one PNG per route x size x theme to a printed folder
   and prints one verdict line (N shots, M failed). A route that errors or times out is a fail.
3. Playwright: use the pre-installed package when `require('playwright')` resolves; else exit
   with one line naming what is missing. Never run `playwright install`.
4. Simulator: when the config names a UDID, take `xcrun simctl io <UDID> screenshot` only if
   the device is already booted. Never boot a simulator (repos ration them). Not booted is a
   skipped row, not a fail.
5. install.sh and install.ps1 copy it as they copy the other bin tools. README: one line.
6. Record: a decision slug file for the script's contract (one per question; slug, no number).

## Failure classes and proof

- Test-author first, red on main: a fixture config with a local static page served on a free
  port; assert PNG count and size, the dark theme differs from light, a 404 route is a fail, a
  missing Playwright gives the one-line exit, and no simctl boot call appears with a stub xcrun.
- False green: a blank page still makes a PNG. Assert a page with known content renders
  non-blank pixels.
- Cost: no daemon, no watcher; one browser process per run, closed at exit.
- Program logic: a fresh Sonnet reviewer reads the diff.

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
