# A commit that adds test lines carries the red run of those lines

## The ruling

`lint/check_red_run.py` is the one home. CI runs it on each pull request (step "Red-run trailer" in `checks.yml`), with `BASE_SHA` set to the PR base. The test-author runs `python3 ~/.claude/lint/check_red_run.py --base origin/main` before it pushes, in whatever repo it works in (`agents/test-author.md`).

1. It reads each non-merge commit in `<base>..HEAD`. A commit that adds lines to a test path needs a trailer in its message: `Red-run: <command> -> <N> failed on <sha>` (N is 1 or more, sha is 7 or more hex digits), or `Red-run: none: <reason>`.
2. A test path is what `is_test_rel` in `hooks/guard.py` judges. The check imports it and keeps no copy.
3. `Red-run: none: <reason>` is for a change that adds no new claim, such as a re-pointed fixture. A reviewer reads each reason, because a junk reason passes.
4. A commit that only deletes test lines needs no trailer. A merge is not judged; the commits it brings in are.
5. Rollout: when the tree at HEAD holds `lint/check_red_run.py`, a commit whose parent tree has no such file is not judged. The commits from before the check landed stay as they are. The check reads this with `git ls-tree HEAD`, never from disk. In a repo whose HEAD has no such file, each non-merge, non-revert commit in the range is judged.
6. The check reads the repo it runs in: the current directory, or the folder `--root <dir>` names. It imports `is_test_rel` from its own install (`../hooks/guard.py` beside the script), never from the repo it reads. Other repos get the check from the installed copy at `~/.claude/lint/check_red_run.py` now. Their CI runs it later, through a separate lane. This repo's CI step stays as it is.
7. A commit whose message has git's `This reverts commit <sha>.` line is not judged. Its lines were judged once already, when the commit it reverts landed.
8. A range git cannot read, or a run with no base, prints UNKNOWN and exits 2. It never exits 0, locally or in CI. This differs from the shape in `ci-unknown-is-red`, where an unknown read exits 0 locally and non-zero only when env `CI` is set.

9. Push time. The guard refuses a `git push` (rule `red-run`, `hooks/guard.py` step 6c2) that sends a non-merge commit that adds test lines with no valid Red-run trailer. It calls `judge` in the one home (`lint/check_red_run.py`), with the range the conflict-markers push check reads and its own `is_test_rel`. The commits the default base holds are left out, so a merge or a rebase of main is not judged; a lane's own test commit is. A commit in the same shell call before the push counts: its `-m` text is read as its message (an `-m "$(cat <<'EOF' ...)"` message is read from its heredoc body, which the guard's heredoc strip leaves out of the command text), an `--amend` with no `-m` keeps the commit's own message, and the test lines it stages are read from the index or the working tree. The refusal for a flagged last commit names only `git commit --amend` and `git push` (the first two lines of the CLI's `REMEDY`). The refusal for a flagged commit below the last prints the trailer forms, then `git commit --allow-empty -m "amend! <sha>" -m "<subject>" -m "Red-run: ..."`, `GIT_SEQUENCE_EDITOR=true GIT_EDITOR=false git rebase -i --autosquash <sha>^` and `git push`, with the flagged commit's sha. When the destination's remote-tracking ref is not an ancestor of the pushed source (the branch was rewritten after its push), the refusal prints no command and says the reword needs the owner. A refusal never names a force push, a branch switch, a cherry-pick or a replacement pull request. A failed read, a default base it cannot read, and a copy of the hooks with no `lint` folder beside it give no hit. A commit whose message comes from `-F`, `-C`, `-c`, `-t`, `--fixup`, `--squash` or an editor gives no hit for the whole push: an untrailered test commit below it is not refused (known limit, below).

Why: the plan found 17 red runs recorded for 29 test changes (`docs/plans/test-ci-standard.md`, standard S5, step 2). A test that was never seen red on the old code may not be able to fail. `agents/test-author.md` names the trailer as the record of the run.

Known limits:

- The check reads that a run is claimed, not that it ran. A reviewer re-runs a claim only when the claim is in doubt (`roles-each-layer-proves-once`).
- A pure rename of a test file reads as a delete and an add, so it needs `Red-run: none: <reason>`.
- A branch that merged a newer main carries main's commits in the range, and the CLI judges each like the rest. The push check leaves out the commits the default base holds.
- The push check reads a commit of the same call from its `-m` text only. A message from a file or an editor, a commit made by a script, and a `rebase --continue` or `merge --continue` before the push are not read, so the push is not judged on them. An `--amend` reads the test lines it stages, not a tree change by another step.
- A commit with `-F`, `-C`, `-c`, `-t`, `--fixup` or `--squash` before the push makes the whole push no-hit, so an untrailered test commit below it, or in it, is sent. Tests pin this as today's behaviour. Reading those forms would cost a file read or one more git call each, and is not built.
- A flagged commit below the last one takes two commands to reword (an `amend!` commit, then an autosquash rebase), not one.
- A reword of a branch rewritten since its push needs the owner, because the push would rewrite pushed history.
- A lane begun before the check landed escapes for its commits from before that, unless it is rebased.
- Conflict-resolution lines in a merge commit are not judged.
- The three mutation tests (`hooks/mutate_guard.py`, `hooks/mutate_shared.py`, `janitor/mutate_sweep.py`) are test content: a builder never edits them, a test-author writes them (owner ruling, 2026-11-08 17:19 CST, waiting-page item 447 a). This check does not judge them. It reads only `guard.is_test_rel`, which does not name them. `AUTHOR_MUTATION_TESTS` in `hooks/guard.py` reaches the builder and test-author checks through `is_mutation_test_rel`; this check does not read it. So a commit that adds lines to one of them needs no trailer.
- The check path is fixed in the check. Renaming the check turns it off.
- In a repo whose HEAD has no `lint/check_red_run.py`, a range that reaches back past the repo's first trailered test commit judges old commits too (item 5). The test-author's `--base origin/main` keeps the range to its own lane.

Risk kind: likely risk, per `building-guard-needs-incident`. Test-author work adds new tests in normal work, and 12 of 29 recorded changes carried no red run. Landed 2026-11-01.

Cost: no long-lived process, no log, no timer. One python process per run, once per pull request run and once per test-author push (unmeasured). It starts these git children. One `log --numstat` reads the range and each commit's files (unmeasured). Only a commit that adds test lines with no trailer costs more: one `ls-tree` of the head, then one of its parent when the head holds the check. The guard's push check adds one `git log --numstat` to every push that reaches a readable base (a `git log`, never a `git diff` of the commits' content), and nothing more when no commit is a gap (unmeasured; the guard's lazy import of the check loads no second guard). A push that carries a gap also reads the default base (once per push), runs a second `log` without the default base's commits, and runs one `git merge-base --is-ancestor` to tell a rewritten branch. A commit before the push in the same shell call costs one `git diff --numstat`, and one `git ls-files --others` for each earlier add that names paths; an `--amend` also costs one `git rev-parse`. A commit with no push after it costs none.

Kind: process
Home: lint/check_red_run.py
