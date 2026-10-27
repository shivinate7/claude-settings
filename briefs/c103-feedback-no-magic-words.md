# c103: your feedback is caught with no magic words (option A)

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 6902807 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor; never merge.

## Goal

Every owner message is captured with no "fb" or "fb done". Ruling: Oct 26 20:57 CDT decision card,
option A now (C later is c104). Brief source: https://claude.ai/artifact/NGf6aaaVp2bF1i3kyhF5HD.

## Inputs

- hooks/local_time.py, hooks/feedback_gate.py, hooks/feedback_judge.py, decision
  owner-feedback-inbox, and the debt notes on close-word edge cases.
- Build: capture every owner message; the Stop jot gate asks for items only on a burst (two or more
  owner messages in a turn, or one message of three or more non-blank lines or two or more bullets).
- Delete fb, fb done, the 10-minute timer and the Sonnet judge, with their tests, settings rows,
  catalog rows and debt notes. Rewrite decision owner-feedback-inbox in place in the same lane.
- A deletion that drops lines needs a `Drops-lines` trailer in the commit message.
- check_landed_dirs, hook_catalog and agent-model-cap rows must follow the deletions.

## Proof

Test-author first: burst and non-burst cases red on main, then green; one-line messages never
trigger the gate. Quick checks: rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check,
check_silent_undo --strict, shellcheck on changed *.sh, `bin/ste-changed origin/main`, and the touched suites.

## Report

At most 25 lines: draft PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer).
Port: yes, hooks install everywhere.
