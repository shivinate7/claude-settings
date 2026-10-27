# c101: a report gate never makes a session send its whole report twice

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 835cde5 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor (read the roster in the project instructions); never merge.

## Goal

When lint/report_gate.py (a Stop hook) blocks a reply, the session sends only the corrected
lines, never the whole report again. Incident: shiv's gripe Oct 26 21:12 CDT, a mailaudit
session printed its full report twice to change BUILT to OTHER and add model names.

## Inputs

- lint/report_gate.py: every block text. The missing-report block already says "Keep the reply
  above it as it stands. Do not write it again." (commit e2ac83bc). Find each other block
  (report shape, model names, Unstarted line, cite gloss, label words) and make its text say:
  post only the corrected lines, as a short correction, never the report again.
- Decision reply-judge-samples-never-blocks: add one line for this gate. Find the record with
  `python3 lint/hook_catalog.py` output or docs/records.md.
- A Stop hook cannot see a reply before it is shown; do not try to make it pre-check.
- Check the gate accepts the short correction as a pass on its next run (a correction-only reply
  must not trip the same gate again). If it would, say so and fix it.

## Proof

Test-author first: one case per block asserting its text tells the session to post only the
corrected lines, red on main; one case that a correction-only follow-up passes. Then green.
Run lint/test_*.py that cover report_gate, `bin/ste-changed origin/main`, and the quick checks:
rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check, check_silent_undo.

## Report

At most 25 lines: PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer;
the diff changes a gate). Port: yes, the gate is global.
