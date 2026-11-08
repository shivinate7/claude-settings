# The lane lint's fast steps run before a push leaves

## The ruling

Rule `lane-lint-push` in `hooks/guard.py` refuses a `git push` when a fast step of CI's lint would fail on the commits the push sends. Its home is `lane_lint_push_hit` in `hooks/guard_merge.py`. It extends the push check that `red-run` and `conflict-markers` share. It adds no second hook. Coordinator, 2026-11-08 08:12 CST: run the lane lint, or its fast checks, before a lane's push.

- The mistake: the silent-undo step failed pull request 1759 after the lane pushed it (lane lane-finds-triage). The same gap sent a test commit out with no Red-run line. A force push is the owner's act, so each such gap costs a replacement pull request.
- The command is the step's own. `lint/workflow_steps.py` reads `.github/workflows/checks.yml` of the checkout. The guard runs each fast step's `run:` text and `env:` in a `bash -e -c` child. It copies no script name and no flag.
- A step is fast when `bin/ci-job`'s own lint chooser, `is_lint`, picks it and its `env:` takes `${{ github.base_ref }}` or `${{ github.event.pull_request.head.sha }}`. The guard loads `is_lint` from `bin/ci-job` and keeps no copy of it. No step is picked by name. A step the chooser leaves out is not read further, so its `if:` and `env:` give no note. The red-run step is left out, because `red-run` judges it in the guard's own process. On a lint step, an `if:` other than the pull-request test, or an `env:` value that is another expression, reads unknown.
- A step that takes the head sha runs on the pushed commit. When origin holds the destination, it runs again on the remote tip. A step that takes only the base ref reads the checked-out HEAD. It runs once, with the destination as its base when origin holds it, else origin's default branch. When the pushed ref is not the checked-out HEAD, it reads unknown.
- A finding is a stdout line that is not indented and is not an `ALLOWED`, `UNKNOWN` or `REMEDY` line. The guard reads those three words from the constants `lint/check_silent_undo.py` exports and prints with. The check prints its remedy as a `REMEDY` line for that reason.
- The pushed head's workflow is the checkout's, or the run is unknown: the child compares the two files and exits with a code of its own when they differ.
- Unknown allows, with one guard.log line and one stderr line that both say unknown. Unknown is a step's own `UNKNOWN` line, a step the guard cannot read, a run past `LANE_LINT_PUSH_SECONDS` (default 40 s, one deadline for the call, under the hook's 60 s), no bash, an odd exit, an exit 1 with no finding line, and a tip run that is unknown when the first run fails. Why: CI still carries every step, and a check that blocks on its own fault cries wolf (`guard-that-cries-wolf-is-spent`). Never the exit code alone: `--strict` exits 1 for an `UNKNOWN`.
- A shallow clone is unknown, and its note gives the remedy `git fetch --unshallow origin`. A cloud lane starts shallow, so it is not linted until it fetches the rest: debt `lane-lint-shallow-unknown` (a shallow clone is never linted at push).
- The refusal names the step and the first finding lines. The remedy: fix what each line names, or for a silent undo put the lines back or add a `Drops-lines: <path> -- <reason>` trailer. An override lifts it.
- Not judged, no process, no note: a dry run, a delete, a tag, a destination `archive/*` or the record branch, a checkout with no `.github/workflows/checks.yml`, and a workflow with no fast step.
- Limits: a push with nothing to send still starts its runs. A `bash -c` script is not read. A stacked lane's first push re-lints its parent's commits: with no remote tip to compare, the range runs from origin's default branch, so a finding in the parent refuses the child's push too.
- The child kill is `kill_tree` in `hooks/_nowindow.py`, shared with `hooks/sendmessage_state.py`.

## Scope

The step's sentence: the guard "runs the lane lint's fast checks on the commits it sends". Each pick below reads it. None is an owner ruling.

- Sent commits only, and a finding already at the remote tip does not refuse. A head-sha step runs on the pushed commit and, when origin holds the destination, on the remote tip. Only finding lines the first run prints and the tip run lacks refuse, compared by text. Lane pick, 2026-11-08 CST.
- Silent-undo's upstream is origin's default branch, CI's base, never the destination's tracking ref. Lane pick, 2026-11-08 CST.
- A pushed ref other than HEAD is linted by its own sha, passed as `HEAD_SHA`. Lane pick, 2026-11-08 CST.
- Unknown allows, as listed above. Lane pick, 2026-11-08 CST.
- Chain: a commit, merge, revert, cherry-pick, rebase, am or pull earlier in the same call, before a push the lint would judge, is denied: "run the push in a call of its own, after the commit lands". The deny is blanket: it does not ask whether the segment would make a commit or what the commit holds. The guard cannot read a commit that has not landed, so it cannot lint what the push sends. The cost is one retry. Lane pick, 2026-11-08 CST.
- A workflow with no fast step, or no checks.yml, is skipped with no note. A repo whose CI has no such step has nothing to lint, and a note on every push would cry wolf. Lane pick, 2026-11-08 CST.
- A shallow clone stays allowed with one stderr line and one guard.log line, and the line names `git fetch --unshallow origin`. Lane pick, 2026-11-08 CST.

## Cost

A call with no push, or a push the list above skips, starts no process. Else per pushed ref, one `bash` child per run: one per step that takes only the base ref, and one per step that takes the head sha, two when origin holds the destination. The runs of a ref start together. Each child's git reads (default branch, pushed commit, workflow compare) and the lint's own reads run inside it, so the guard starts no git of its own for them. The top folder comes from the record-branch check's read. `bin/ci-job` and `lint/check_silent_undo.py` load as modules once per call, on the first judged push, and start no process. No log, file or lasting process.

- This repo's workflow has three fast steps (ruling kind, silent undo, comment narration). A push to a new destination starts 3 children. A push to a destination origin holds starts 4.
- The test fixture's workflow has one fast step (silent undo). Its guard launch counts: 11 for a clean push to a new destination (10 before the lane lint, 1 child), 7 to an existing one (5, 2 children), 9 for a non-push call. Cases 8a to 8c of `hooks/test_guard_lane_lint_push.py` prove them.

## Measured

- The guard's whole run over 7 lane tips (0 to 51 commits, 0 to 26 files each): a push to a new destination took 0.31 to 2.47 s (median 1.00 s, n 7). A push to an existing one took 0.61 to 2.10 s (median 0.90 s, n 7).
- Each step alone, over 13 lane ranges (n 13): silent-undo 0.07 to 2.02 s, ruling-kind 0.04 to 0.08 s, comment-narration 0.12 to 2.13 s.
- Budget: 10 s of lint time per push. All three fit, so none is left out.

Protected by `hooks/test_guard_lane_lint_push.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
