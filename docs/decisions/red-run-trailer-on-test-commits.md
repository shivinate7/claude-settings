# A commit that adds test lines carries the red run of those lines

## The ruling

`lint/check_red_run.py` is the one home. CI runs it on each pull request (step "Red-run trailer" in `checks.yml`), with `BASE_SHA` set to the PR base. The test-author runs `python3 ~/.claude/lint/check_red_run.py --base origin/main` before it pushes, in whatever repo it works in (`agents/test-author.md`).

1. It reads each non-merge commit in `<base>..HEAD`. A commit that adds lines to a test path needs a trailer in its message: `Red-run: <command> -> <N> failed on <sha>` (N is 1 or more, sha is 7 or more hex digits), or `Red-run: none: <reason>`.
2. A test path is what `is_test_rel` in `hooks/guard.py` judges. The check imports it and keeps no copy.
3. `Red-run: none: <reason>` is for a change that adds no new claim, such as a re-pointed fixture. A reviewer reads each reason, because a junk reason passes.
4. A commit that only deletes test lines needs no trailer. A merge is not judged; the commits it brings in are.
5. Rollout: when the tree at HEAD holds `lint/check_red_run.py`, a commit whose parent tree has no such file is not judged. The commits from before the check landed stay as they are. The check reads this with `git ls-tree HEAD`, never from disk. In a repo whose HEAD has no such file, each non-merge, non-revert commit in the range is judged.
6. The check reads the repo it runs in: the current directory, or the folder `--root <dir>` names. It imports `is_test_rel` from its own install (`../hooks/guard.py` beside the script), never from the repo it reads. Other repos get the check from the installed copy at `~/.claude/lint/check_red_run.py` now. Their CI runs it later, through a separate lane. This repo's CI step stays as it is.
7. A commit whose message has git's `This reverts commit <sha>.` line is not judged. Its lines were judged once already, when the commit it reverts landed. A commit whose tree equals the tree of one of its ancestors is not judged either, with or without that line: it writes back a tree that was reviewed. An ancestor is any commit reachable from the commit's parent, main's history included, never a sibling branch. The read runs only for a commit that would otherwise be a gap, and takes at most 5,000 ancestors (`MAX_ANCESTORS`). A failed read, or a cap reached with no match, leaves the gap (incident: a combined revert to a reviewed tree was refused, pull request 1671).
8. A range git cannot read, or a run with no base, prints UNKNOWN and exits 2. It never exits 0, locally or in CI. This differs from the shape in `ci-unknown-is-red`, where an unknown read exits 0 locally and non-zero only when env `CI` is set.
9. Push time. Rule `red-run` in `hooks/guard.py` refuses a Bash `git push` that sends a commit item 1 flags. It adds no second judge or base: `_push_hit` in `hooks/guard_merge.py` reads the base that the conflict-markers push check accepted (`_checked_range` returns it). It calls `gaps(root, base, head, exclude, is_test_rel=...)` with the pushed source ref as the head and the guard's own `is_test_rel`. So `check_red_run` imports no `guard` there; the CLI passes `guard.is_test_rel`. The lane's own commits are judged. Commits the default base holds are not, so a merge or rebase of main brings in none. When the default base cannot be read, the push check gives no hit rather than judge main's commits. The rollout (item 5) reads the pushed source's tree. A failed read is no hit, in either `gaps` call, and so is a copy of the hooks with no `lint/` folder beside it. The refusal names this decision and quotes the first two lines of the check's printed remedy (the `REMEDY` constant). The third line names a branch switch, which no refusal names (rule `git-remedy-never-names-target`).

Why: the plan found 17 red runs recorded for 29 test changes (`docs/plans/test-ci-standard.md`, standard S5, step 2). A test that was never seen red on the old code may not be able to fail. `agents/test-author.md` names the trailer as the record of the run.

Known limits:

- The check reads that a run is claimed, not that it ran. A reviewer re-runs a claim only when the claim is in doubt (`roles-each-layer-proves-once`).
- A pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`.
- A branch that merged a newer main carries main's commits in the range. The push check leaves out the default base's commits, and the CLI still judges them under `--base`.
- The push check reads the unpushed range only. A commit pushed before the rule landed, or by a tool call the guard does not read (a script, `sh -c`), is judged by CI alone. It reads no branch that `--all`, `--mirror` or `--tags` with no refspec sends. A repo whose default base cannot be read gets no push-time hit, so CI judges its commits.
- A lane begun before the check landed escapes for its commits from before that, unless it is rebased.
- Conflict-resolution lines in a merge commit are not judged.
- Mutation tests are not test paths, so they need no trailer.
- The check path is fixed in the check. Renaming the check turns it off.
- In a repo whose HEAD has no `lint/check_red_run.py`, a range that reaches back past the repo's first trailered test commit judges old commits too (item 5). The test-author's `--base origin/main` keeps the range to its own lane.

Risk kind: likely risk, per `building-guard-needs-incident`. Test-author work adds new tests in normal work, and 12 of 29 recorded changes carried no red run. Landed 2026-11-01. Item 9 mistake: lane page-reply-uncollapse pushed a test commit with no `Red-run:` line on 2026-11-07. The gap showed only at the merge lint, so the fix was a replacement PR.

Cost: no long-lived process, no log, no timer. One python process per run, once per pull request run and once per test-author push. It starts these git children. One `git log --numstat` reads the range and each commit's test files. When a non-revert commit with test lines and no trailer turns up, one `ls-tree` reads the head's tree. When the head holds the check, one `ls-tree` per such commit reads its parent. Each commit that is still a gap then costs one `git log -n 5000 --format=%T <parent>`. That is at most 205 KB of tree ids, and about 0.1 s. This repo's 2,900 commits took 45 ms (2026-11-08, one run). A range with no such commit costs the `log` alone.

Push-time cost (item 9): one more `git log` per `git push` the guard reads, with the same shape as above, and nothing else when the range holds no gap. A push that carries a gap costs more. It adds the `ls-tree` reads and one ancestor-tree `git log` per commit that is still a gap (item 7). It adds the default base's reads once (`git symbolic-ref` and `git rev-parse` per candidate, shared with the conflict check when it needed them). It adds a second `git log` without the default base's commits. The hook imports `check_red_run` at the first push that reaches it, which starts no process and loads no second `guard`; the import measured 0.4 ms (2026-11-07, one run). No log, timer or long-lived process. `record_push_cost_case` in `hooks/test_guard.py` pins the no-gap spawn counts.

Kind: process
Home: lint/check_red_run.py
