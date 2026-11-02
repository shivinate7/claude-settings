# Handoff: no-undo-lane-commits

## Goal

Stop builders from undoing earlier work of their own lane (owner ruling fb-1041-1, 2026-11-02 10:41 CST).
Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U.

## Rulings

- One excuse line, `Drops-lines: <path> -- <reason>`. No `Removes:` (owner, 2026-11-02 10:52 CST, page
  item 165, pick a). Home: docs/decisions/silent-undo-check-design.md.
- Narrow the read to two shapes (coordinator, 2026-11-02 11:26 CST). The owner's grant is pending on his
  page, because it narrows his "any line".

## State

- Branch `no-undo-lane-commits`, head 43dfc3b0 before this handoff commit.
- PR #1099 (lane undo check), draft. Review round 1: FAIL, 9 findings (reviewer haiku). Round 2 builder
  (sonnet) fixed findings 1-5 in 43dfc3b0. The test-author (haiku) fixed findings 6, 7 and 9 in 0742780d
  and 6eeb70e9. The orchestrator fixed finding 8 in 8fdaff2e. Review round 2 has not run.
- Nothing unpushed. Not yet sent to batch runner 7.

## Done

- lint/check_silent_undo.py: the lane undo read. merge/merge.py: the tool's claim revert carries the
  excuse line, with the word read from the check's `TRAILER`.
- agents/builder.md, skills/project-ops/templates/brief.md, CLAUDE.md `roles-brief-contents`: edit in
  place, run the check after each commit, a `Keep:` line in round 2 and 3 briefs.
- Red proof: before the lane, both `--upstream 4477f7e3 --head 3297d8fa` and
  `--upstream 792ede51 --head df25a68d` exit 0. At 43dfc3b0 both exit 1.
- Restore count command (19 for the measured window):
  `git log origin/main --no-merges --since=<start> --until=<end> --format=%s | grep -c -i -E 'restor|re-add|undid'`

## Next

1. Re-measure the sweep. At 43dfc3b0 it reads 16 of 31 batches red, 62 findings (54 hunk), against 9 red,
   10 findings at a05026cf. The finding-2 fix (net loss counts partial drops) made it loud again. Sweep:
   for each `m` in `git log origin/main --first-parent --merges --since=2026-10-31T00:00-05:00 --format=%H`,
   run the check with `--upstream $m^1 --head $m^2`.
2. Pick a net-loss dial: builder measured 41 findings in 15 batches at 3 lines, 29 in 13 at 6 lines.
3. Read 43dfc3b0, an empty commit with two `Drops-lines:` lines for lint/test_check_silent_undo.py and
   merge/test_merge.py. Confirm each excuse is true, or remove it.
4. merge/test_merge.py after the last rebase: result unknown. Run it once.
5. Review round 2 (reviewer sonnet), `~/.claude/bin/merge --lane-lint 1099`, then send the number, head
   and verdict to batch runner 7 and the coordinator.

## Open questions

- Owner: narrowing "any line" to two shapes (on his page, via the coordinator).
- Owner or coordinator: the net-loss dial (step 2).
