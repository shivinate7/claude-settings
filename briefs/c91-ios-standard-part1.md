# c91 part 1: one iOS standard page and a new-app starter in claude-settings

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main e305bdb or newer.
claude-settings only: read other repos for reference, never push to them. Never rebase onto main
after review. Send the green, reviewed head to the build advisor; never merge.

## Goal

One "iOS apps" page in claude-settings sets the standard every iOS repo follows, plus a starter
for a new app, plus compliance-check rows that flag drift.

## Inputs

- Plan: the iOS kit consultation report, /mnt/project-files/reports/ios-kit-consultation.html.
  Read its gold-standard column.
- The standard: the same make targets (phone, testflight, native-check); logic in an in-repo Swift
  package; XcodeGen; Swift 6; CI pinned to macos-26 that runs package tests and compiles every app;
  slow tests once per batch on the Mac through bin/sim-test (c89, in batch #663); tokens.json
  generated into Swift; shiv's ruling Oct 22 "Mac install first, TestFlight fallback, every app"
  (today recorded only in mailaudit; give it a home here as a decision).
- Reference repos to read: home-app, mailaudit, ios-adblock, degen. Known drift: home-app CI on
  macos-latest; ios-adblock in Swift 5.0 mode.
- Starter: sets up project.yml, the make targets, a Kit package, the CI workflow and a bin/ios-ship
  entry. It must run from a clean folder and its own test proves the generated tree.
- Deferred, not in this lane: the repo visits and the install-timing rule (both wait on shiv).

## Proof

Starter test red first, then green. compliance-check rows each go red on a fixture with the drift
they flag. Run `bin/ci-job gates --base origin/main` once (background, 90-minute timeout) and
`bin/ste-changed origin/main` before you report.

## Report

At most 25 lines: PR, head, proofs, gates verdict per failing or unknown step, reviewer verdict.
Portability call: yes, every iOS repo (already ruled on the step).
