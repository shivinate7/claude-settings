# c109: a blind design brief is built from a template that cannot carry today's screen

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 6902807 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor; never merge.

## Goal

A blind designer lane never sees the current screen. Incident: Oct 26 22:58 CDT, every Duo mockup
for mailaudit copied the current app; its one brief named today's views and a keep rule.

## Inputs

- skills/design-explore/SKILL.md (d10, blind, informed and directed designer lanes), agents/designer.md,
  skills/design-review/SKILL.md.
- (1) design-explore builds each blind brief from a fixed template: the user's job in their words,
  the device and its poses, the house rules and the brand palette only.
- (2) A stdlib check refuses a blind brief that names a current view, a screenshot or mockup path,
  the spec, or a keep or match rule; and refuses an explore run with no blind lane unless the owner
  asked for none. Wire it where design-explore writes briefs.
- (3) design-review flags a mockup set that all share today's structure.
- New check: check_landed_dirs, hook_catalog and rule_audit as they require.

## Proof

Test-author first: the Duo brief as a fixture, refused red-first; a clean blind brief passes.
Quick checks: rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check,
check_silent_undo --strict, shellcheck on changed *.sh, `bin/ste-changed origin/main`, and the touched suites.

## Report

At most 25 lines: draft PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer).
Port: yes, skills install everywhere.
