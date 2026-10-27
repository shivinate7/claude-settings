# c106: a label or status word appears once per screen

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 6902807 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor; never merge.

## Goal

On any screen, a label or status word ("blocking", "upcoming", "whenever") appears once; every
other place uses its shape or colour. Owner gripe, Oct 26 20:40 CDT: too much verbiage.

## Inputs

- docs/design/ (installed to ~/.claude/docs/design/): add the screen rule to the right file
  (principles.md or checklist.md), STE, fewest words.
- agents/design-reviewer.md and skills/design-review/SKILL.md: the reviewer checks it on each screen.
- If a cheap stdlib probe can count repeated label words in a rendered page's text, add it to the
  design-review steps; otherwise mark the rule judgment in rule_mechanisms.json.

## Proof

If a probe lands: a fixture page with "blocking" three times, red first, then green. Otherwise
the docs and agent checks only. Quick checks: rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check,
check_silent_undo --strict, shellcheck on changed *.sh, `bin/ste-changed origin/main`, and the touched suites.

## Report

At most 25 lines: draft PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer).
Port: yes, every repo with screens.
