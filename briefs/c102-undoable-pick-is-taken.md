# c102: a question whose pick can be undone is taken, not asked

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main 835cde5 or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor; never merge.

## Goal

A session that has a question with a safe pick that can be undone takes that pick, names it under
Done, and does not ask. It asks only when the pick cannot be undone or changes the owner's goal.
Incident (coordinator, Oct 27): a mailaudit report asked "link the waiting page now with a folder
move, or later"; "later" changed nothing and could be undone.

## Inputs

- CLAUDE.md rule questions-go-to-owner and its decision docs/decisions/questions-go-to-owner.md:
  amend in place, in STE, fewest words. Keep c84's and c98's sentences.
- Rule parallelism-keep-going (follow-ups found by the session) already says the same for
  follow-ups; cite it, do not duplicate it.
- hooks/reply_judge.py: add a judged note (never a block; decision
  reply-judge-samples-never-blocks) for an Input Needed item whose pick the judge reads as
  undoable. Keep its cost as the decision states it.
- rule_audit pins: if the amended rule changes its mechanism count, move the pin in the same commit
  and say why.

## Proof

Test-author first: reply-judge fixture cases red on main (an undoable-pick question flagged; an
irreversible one and a goal change not flagged), then green. Quick checks: rule_audit,
test_check_glossary, check_mod_versions, hook_catalog --check, check_silent_undo,
`bin/ste-changed origin/main`, and the reply-judge suite.

## Report

At most 25 lines: PR, head, red-run proof, verdicts, reviewer verdict (fresh Sonnet reviewer).
Port: yes, global rule.
