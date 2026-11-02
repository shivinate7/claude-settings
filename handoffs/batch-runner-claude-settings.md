# Batch runner handoff: claude-settings

Written by batch runner 7 at wind-down, 2026-11-02, for the next batch runner on
shivinate7/claude-settings. Read the live state before you act: this file is a snapshot.

## State at handoff

- main: 5a5f081e (batch 69, #1103, merged 13:12 CST Nov 2).
- Batch 69: MERGED as #1103 with #1061 (0e8edd82), #1097 (a48712f5) and #1101 (0bbbc1e3). #1070 was dropped on red checks-mutate-guard. #1102 was closed and replaced by #1103. No batch is open, and batch 70 has not started.
- Open PRs: `gh api "repos/shivinate7/claude-settings/pulls?state=open&per_page=60" --jq '.[]|"\(.number) \(.draft) \(.head.sha[0:8]) \(.head.ref) | \(.title)"'`

## Batch queue

| PR | Head | Review | State | Why it waits |
|---|---|---|---|---|
| #1070 questions-reach-page | 7373ce61 | lane review passed | ready after fix | Dropped from batch 69 on red `checks-mutate-guard`. Its conflict fix moved #1095's own-session tag rule into hooks/own_session.py, so the mutation at hooks/mutate_guard.py:1996 ("roadmap-one-writer: a set_session_tags call on another session voids the own proof") lost its anchor. The lane must re-point that mutation and run `python3 hooks/mutate_guard.py` in full. |
| #1065 review-record | 42fdc267 | round 1 FAIL, round 2 PASS (record on the PR, at head 1df70a69) | needs a main merge | Conflicted with #1061 in merge/merge.py, and #1061 is now on main 5a5f081e. The lane merges main, resolves merge/merge.py, and sends a head. Confirm the review record covers that head. |
| #919 tier-boundaries-enforced | 568e606e | n/a | HELD by the coordinator (10:17 CST Nov 2) | Its guard reads a role file that main no longer writes for the coordinator, so it would never fire. A fix lane runs. Never take head 01bb1125. |
| #1042 coordinator-acts | 49adc89e | n/a | HELD with #919 | Contains #919. |
| waiting-data-in-repo (PR not open at handoff) | n/a | n/a | OWNER HOLD (owner chat, 11:00 CST Nov 2) | Never batch or merge it until the owner says merge. |
| #1100 page-title-cockpit | 6e5e38ce | round 1 FAIL, round 2 PASS (reviewer sonnet); design review PASS at all 6 cells | READY for the next batch | Arrived at 12:41 CST during the wind-down. Its lane (session_013NEJL1fXkpTkTyXnWoLpvb) got no reply, because the coordinator said to message no other session. |
| #1098, #1099 | see query | unknown | not sent to the batch runner | Their lanes had not sent a head at handoff. |
| #1008, #1034, #1036, #1049, #1051 | see query | n/a | plan or record drafts | Not lane code. They wait on owner answers or the coordinator. |

## How a batch runs

1. After each container resume: `get_session` with no arguments, in a turn of its own, then `~/.claude/bin/merge --role batch-runner`.
2. Build in a worktree: `git checkout -b batch-N origin/main`. Fetch each head with `git fetch origin +refs/pull/N/head:refs/remotes/pr/N`, then run `git merge --no-edit pr/N` per lane. On a conflict, list the files with `git diff --name-only --diff-filter=U`, then run `git merge --abort`. Lanes can clash with each other even when each is clean on main. Try orders, and keep the one that fits the most lanes.
3. Pre-checks: `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict` must return rc 0, because CI runs it. `python3 lint/hook_catalog.py --check` may report only "docs/records.md is stale".
4. Local checks, in parallel, each through `~/.claude/bin/verdict`: `~/.claude/bin/ci-job checks --lint`, `python3 hooks/test_guard.py`, `python3 merge/test_merge.py`, `sh hooks/test_install_src.sh`, `python3 hooks/test_sendmessage_state.py`, `python3 hooks/mutate_guard.py`, `python3 janitor/mutate_sweep.py`. The last three are outside the lint job. Batch 68 went red on the first and batch 69 on the second.
5. Push, open a DRAFT PR, and subscribe to it. Then run `~/.claude/bin/merge <n> --confirm` in the foreground with no pipe. That rebuilds docs/records.md and keeps the draft. Never commit docs/records.md yourself.
6. Mark it ready: `gh api -X POST repos/shivinate7/claude-settings/pulls/<n>/ccr/ready_for_review`. Then run `merge <n> --confirm` in the background (timeout 5400000) and set a send_later check-in about 45 min out.
7. On a red run: read the failing job's log, find the lane by its files, and drop it by rebuilding from main. Never revert, and never fix on the batch branch. Push with `--force-with-lease`.

## Merge-tool notes

- A lane DROP after the PR is ready loses the records commit. The tool then refuses: "the records page on the ready #N is stale". A cloud session cannot return a PR to draft. So open a fresh draft PR from the same branch, close the old one with a comment, and run step 5 again. Batch 69 moved from #1102 to #1103 this way.
- A lane FIX after ready keeps the records commit: fast-forward the batch branch, merge the new lane head, and push plainly.
- A cancelled scheduled run on an OLD main sha used to make the tool refuse with "main UNKNOWN". #1092, merged in batch 68, fixes that read. If it recurs, re-run that run once and retry.
- The waiter guard refuses poll loops and Monitor with sleep. Use send_later check-ins.
- A Drops-lines trailer covers a whole path, so also run silent-undo on the batch without that lane.
- Accept lint reds only when they come from the records page. A stale docs/catalog.md, a rule audit, a Red-run trailer, comment narration and code-check reds are real lane defects.
- On #1102's first head, janitor/mutate_sweep.py killed 0 of 187 mutants in CI. Main passes it, and it killed 187 of 187 locally on the batch 69 head without #1070. The cause is unknown.

## Pace numbers

Send four at each batch merge: (1) wall-clock from the first lane commit to the merge (`git log --no-merges --format='%cI %h' <prev-main>..origin/main | sort | head -1`); (2) lanes run, and the most running at once; (3) minutes with no lane running, and the reason, or "unknown"; (4) in a cloud session, "n/a (cloud)".

None owed. Batch 69 pace, already sent to the coordinator: (1) 14 h 28 min, from the first lane commit c61a42f0 at 22:44 CST Nov 1 to the merge at 13:12 CST Nov 2; (2) 3 lanes merged, 4 entered the run (#1070 dropped), most at once unknown; (3) idle minutes unknown; (4) n/a (cloud).

## Cleanup owed

- Remote branches the cloud refused to delete: inbox-send-debts, one-inbox-per-repo-record, worktree-agent-a60adb…, batch-63c, 63e, 63f, 64d, 65b, 66c, 67, 68 and 69. A session on the owner's computer deletes merged ones under the standing grant in .claude/CLAUDE.md.
- #1102 is closed and replaced by #1103. Lanes #1061, #1097 and #1101 should close as replaced by #1103. Their lanes were not told, because the wind-down allows no messages to other sessions.
