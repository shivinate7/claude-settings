# c110: a lane dropped from a batch never loses its files when it merges main

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 6902807 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor; never merge.

## Goal

Dropping a lane from a batch never puts a removal commit on main. Incident (Oct 27): batch #663
dropped c88 by reverting its merge; when the lane later merged main, the revert silently deleted
11 of its 13 files.

## Inputs

- CLAUDE.md rule git-integration-branch-merge and its decision: say a lane is dropped by
  rebuilding the batch branch from main without it, never by a revert. Add one sentence: a lane
  dropped before this rule re-applies its diff after it merges main, and checks that every file
  survives. Amend in place, STE, fewest words. o13 lane C also edits this rule's paragraph; keep
  your edit small so the batch merge is easy.
- merge/ tooling: if merge.py or its preview can see a revert of a lane merge in the batch range,
  refuse with a remedy that says "rebuild the branch without the lane". If no clean hook point
  exists, say so and ship the rule alone.
- rule_audit pins: move them in the same commit if the mechanism count changes, and say why.

## Proof

Test-author first: a merge test red on main for a batch range holding a revert of a lane merge,
then green; a plain batch still passes.
Quick checks: rule_audit, test_check_glossary, check_mod_versions, hook_catalog --check,
check_silent_undo --strict, shellcheck on changed *.sh, `bin/ste-changed origin/main`, and the touched suites.

## Report

At most 25 lines: draft PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer).
Port: yes, global rule.
