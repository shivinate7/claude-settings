# c73: the phone profile job names a save timeout, not "unlock the phone"

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main be4b30e. Never
rebase onto main after review. claude-settings only. Push roadmap edits to the branch only; only
Triage the roadmap (3) republishes.

## Finding

Liaison, Oct 26, c48 part 2 on the Mac: when xctrace hangs while saving after a full recording
(exit 124 at the step timeout, seen once with HomeApp), `bin/ios-ship profile` says "failed twice"
and that the phone may need unlocking. That is wrong there.

## Task

In bin/ios-ship (the retry c48 part 1 added): print the unlock hint only when the second failure
also shows the boot-wait text; otherwise name the step timeout (exit 124) and the step that hung.

## Proof

- Red first in lint/test_ios_ship.sh: a stubbed exit-124 run with no boot-wait text names the
  timeout and no unlock hint; a boot-wait failure twice still gives the unlock hint (false-alarm
  case). ShellCheck and STE clean. CI's shell-macos job runs it.
- A fresh Sonnet reviewer reads the diff.

## Report

Cap 10 lines: Done, Deviations, Next, "Port to other repos: yes or no, and why". Send the green,
reviewed head to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft.
