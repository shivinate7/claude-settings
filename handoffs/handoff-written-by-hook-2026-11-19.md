# Handoff: lane handoff-written-by-hook, 2026-11-19 00:30 CST

## Goal

Owner ruling 2026-11-13 22:52 CST (relayed by the consultant, started by the coordinator at 22:54 CST): at each handoff checkpoint and after each compaction, Stop is refused until the session has spawned one Sonnet subagent that rewrites its handoff from the transcript since the last write plus the prior handoff. No `claude -p`, no new process, no new log.

## Where things stand

- Slug: `handoff-written-by-hook`. Branch on origin: `handoff-written-by-hook`, head d10d4f9427a90c6cb5a711881944bbb94da52097. It holds the work; git keeps it.
- PR #3364 (draft): CLOSED, not merged. Triage closed it 2026-11-15 18:38 UTC as a stale draft ("silent 24 h or more, not proven dead"; reopen if live). REST 2026-11-19 00:30 CST: state closed, merged false, mergeable_state dirty.
- Draft #3202 (owner-waits section, overlaps the same files) MERGED. So #3364 now conflicts with main again: merge main, re-lint, re-run tests before reopening.
- The one lane PR was never marked ready or merged. Runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) was handed the PR at d10d4f942 on 2026-11-14 01:10 CST, copy to the coordinator. No merge reported.

## Done

- Red tests (test-author haiku): 40 red on 82469ae58, `check_red_run` PASS.
- Gate in `hooks/precompact_handoff.py`, prompt steps 3-4 (builder sonnet). Stop is refused until a main-session Sonnet spawn whose brief names the handoff path returns without error and leaves a newer handoff. Cap 3 refusals per checkpoint and per compaction in `<session>.nudge.json`, then Stop passes with a stderr line (fail open: never a loop).
- Decision `precompact-handoff` item 4 rewritten in place, items 2, 6, 16 touched only where they contradicted it; two debts and four notes (record-writer haiku).
- Review: round 1 FAIL at 57459418c (reviewer haiku), fixed. Round 2 PASS at e134792be (reviewer sonnet), no safety hole.
- Verdicts at d10d4f942: `test_guard.py` PASS 9680 of 9680 (9 skipped); `check_red_run` PASS; at c71657008 `test_precompact_handoff.py` and `bin/ste-changed` PASS. CI at the head: every non-skipped job green; `all-jobs-passed` and 29 other jobs skipped on the draft, so the required check never ran (unknown).

## Unfinished

- #3364 is closed and dirty. Needs: reopen (or a new PR from the branch), merge main, re-run `test_precompact_handoff.py`, `test_guard.py`, lint, read CI with `all-jobs-passed` actually run (mark ready only by the batch runner).
- Debts, unfixed by design: `handoff-old-compact-false-alarm` (sessions that compacted before deploy are refused up to 3 times at first Stop) and `handoff-brief-path-form` (a `~` path in the brief does not count). Triage filed follow-up step `handoff-hook-false-alarms`, blocked on #3364 merging; it also holds step `refusal-names-way-out` and a measure that needs a Mac session.
- Not measured: a real `compact_boundary` record's fields in a live session (the gate no longer depends on its timestamp); the cost of the second transcript read per Stop.

## Next step

Whoever picks this up: confirm the owner still wants the gate (the PR sat silent over 24 h and was closed by triage, not rejected). If yes, reopen #3364 or open a new draft from branch `handoff-written-by-hook`, merge main, re-verify, hand to the batch runner.

## Refused acts

- Agent spawn without a model field was refused twice (builder: "names no model, role has none"; reviewer round 1 with `model: sonnet`: "above the role's model"). Fix used: builder with `model: sonnet`; round-1 reviewer with no model field (runs the role's model, haiku).
- Git worktree creation under `.claude/worktrees/` was refused for the test-author; it worked from a git archive copy.
- No push, merge or comment was refused.

## Owner rulings I hold

- 2026-11-13 22:52 CST (relayed, unverified by me): the subagent gate replaces the `claude -p` option. Home: decision `precompact-handoff` item 4, on branch `handoff-written-by-hook` only (not on main).
- Owner order 2026-11-19 00:19 CST (relayed by the coordinator): hand off, commit to `archive/handoff-<slug>`, wind down. This file is that.
- Picks that are not the owner's word: pick A (merge as is, fix the two debts in a follow-up) was triage's undoable pick, 2026-11-14 23:51 CST.

## Agents (all ended; worktrees may be gone)

- test-author haiku, aacf5f6aa79b5b402, branch `worktree-agent-aacf5f6aa79b5b402`.
- record-writer haiku, a7e4a73288e31f763, branch `worktree-agent-a7e4a73288e31f763`.
- builder sonnet, abfd8b6ca49536c20, branch `worktree-agent-abfd8b6ca49536c20`.
- reviewer round 1 haiku, abb75033002a0a42a, branch `worktree-agent-abb75033002a0a42a`.
- reviewer round 2 sonnet, a05e191ef1311bdf5, branch `worktree-agent-a05e191ef1311bdf5`.
- Work of all five is pushed on `handoff-written-by-hook`.

## Files and commands

- Branch `handoff-written-by-hook`: `hooks/precompact_handoff.py`, `hooks/precompact_handoff_prompt.md`, `hooks/test_precompact_handoff.py`, `docs/decisions/precompact-handoff.md`, `docs/debts/handoff-old-compact-false-alarm.md`, `docs/debts/handoff-brief-path-form.md`, `docs/debts/notes.md`.
- `verdict python3 hooks/test_precompact_handoff.py`; `verdict python3 hooks/test_guard.py` (about 26 minutes; run it in the background and wait); `verdict bin/ste-changed origin/main`; `python3 lint/check_red_run.py --base origin/main`.
- State check: `gh api repos/shivinate7/claude-settings/pulls/3364` (REST).
