# Handoff: lane batch-build-log-kept, 2026-11-19 00:27 CST

Written on the coordinator's wind-down order (owner order 00:19 CST, relayed 00:26 CST). Parent session: the coordinator, `session_013NEJL1gw6EdrSyvHkTUEx6`. This lane: `session_013NEJL3zeWnjihGXaU7aKYE`.

## Slug, branch, head

- Slug: `batch-build-log-kept` (roadmap step of the same name, branch `roadmap`, file `roadmap/data/steps/batch-build-log-kept.json`).
- Work branch on origin: `batch-build-log-kept-r2`, head `c730fe6fe`. It holds every commit of the lane: red tests, builder commits, notes and the record.
- Base when built: main at `2deb827ad`.

## Pull requests

- #2820 "A batch build keeps its log under state/": CLOSED, not merged, draft, `mergeable_state` dirty. Closed 2026-11-16 (GitHub says `closed_at` 2026-11-16T20:04:57Z). I did not close it and did not read why. Head at the close: `c730fe6fe`.
- No other PR is open from this lane.

## Done

- `merge --batch-build` writes `<config dir>/state/batch-build/NAME.log`: a start line before any read, every `say()` line, one end line (`end: ok`, `end: refused: ...`, `end: failed: ...`; a SIGKILL leaves none, by design).
- `--ready` runs ci-job with `VERDICT_LOG` set to that log, and `TMPDIR`, `TEMP`, `TMP` set to `state/batch-build/NAME.tmp/`. The timeout line `ci-job did not finish in N s` is written to the log, and the Stop text names the log path.
- The build keeps the newest 20 logs, each pruned with its `.tmp` folder. The build never prunes its own.
- Functions touched in `merge/merge.py`: `batch_build`, `batch_build_run`, `ci_job_run`, `say`, new `batch_build_log_path`, `batch_tmp_path`, `batch_log_note`, `prune_batch_logs`, `batch_build_log`, `first_line`. One equal-meaning hunk near batch order (`numbers = numbers or ...` became `if not numbers:`). The stack check, `sync_batch`, `build_integration_branch`, `bin/ci-job` and `hooks/stall_watch.py` are untouched.
- Record: `docs/decisions/batch-build-log-kept.md` (cause, home, named reader, cost). Three notes in `docs/debts/notes.md`: `rulings-kind-home-line-false-alarm`, `batch-build-no-end-on-interrupt`, `batch-build-timeout-names-log-only`.
- Tests: 8 new cases in `merge/test_merge.py` class `BatchFreeze`, each red on the old code, then green. They include a real SIGKILL and the real `janitor/temp_sweep.py` run.
- Review: round 1 FAIL (two points), round 2 PASS on `a102496ba` with two low findings. Review record posted as a comment on #2820 at `c730fe6fe`.
- Lane lint on `c730fe6fe`: PASS, every check (run 2026-11-12 11:36 CST).

## Cause of batch 104's death

Unmeasured. Runner 10 reported it ran in a Linux cloud container, ended about 10:24 CST on Nov 12 with nothing pushed, and its log was lost because it was not tee'd. The Windows sweep (`janitor/temp_sweep.py`, 24 h idle) did not remove it. The 3600 s lint timeout printing no log path is a separate gap that this lane closes.

## Unfinished

- The step `batch-build-log-kept` has not landed on main. #2820 is closed and conflicts with main now. `merge/merge.py` has since changed under other lanes, so a rebase may need a read of `batch_build` and `ci_job_run` first.
- Two low findings are kept as notes only: Ctrl-C or SIGTERM leaves no end line; after a kill, parallel step output sits in `NAME.tmp/` and the timeout Stop text names only the log.

## Next step

1. Ask why #2820 was closed. If it was closed on purpose, stop; the work stays on `batch-build-log-kept-r2`.
2. If the step is still wanted: merge main into `batch-build-log-kept-r2`, resolve conflicts in `merge/merge.py` and `docs/debts/notes.md`, run `merge --lane-lint` on a fresh draft PR, post a fresh review record at its head, hand to the batch runner.

## Refused acts

- Kill of orphan lint steps 10336, 10340, 10740, 10743 (left by a test-author agent in this container): refused by guard `machine-wide-kill` at 2026-11-12 17:01 and 17:08 UTC (guard.log), and by the auto-mode classifier (Interfere With Workloads). Left to end on their own; the container is ephemeral.
- Edit hook `rulings-declare-kind` (prose judge) refused four rewordings of line 15 of the record from the builder agent. The reword went through from this session after the owner's `override`.
- `ps` with full arguments, refused by `process-args`; `cd` into another checkout and an Edit in another checkout, refused by `other-checkout`; `verdict | tail`, refused by `verdict-pipe`; a foreground `sleep`, refused by `waiter`; a model field above the role's model, refused by `agent-role-model` (twice, then dropped the field).

## Owner rulings held

- Owner `override` typed 2026-11-12 11:38 CST: one act, until 11:48 CST. Used for the line 15 reword (done; commit `c730fe6fe`). Nothing else rests on it.
- Coordinator rulings (relayed): push and open the draft PR (11:21 CST Nov 12); try wordings that avoid `Home:` first; leave the orphans alone.
- No other ruling held.

## Agents (all finished, none running)

| Agent name | Role, model | Branch or commit |
| --- | --- | --- |
| a9d1ea4523a6d0cd6 | test-author, haiku | `466ee36a8` on `worktree-agent-a9d1ea4523a6d0cd6` |
| a36596f5be2ae7278 | builder, sonnet | `f3cf86a72` on `worktree-agent-a36596f5be2ae7278` |
| a16f21f1baa8eaaac | test-author, haiku | `7c1bcf5f7` on `batch-build-log-kept` (local only) |
| a88d28df9d322e68d | reviewer, haiku (round 1) | none (read-only) |
| ab1320d1a422284eb | test-author, haiku | `615c828aa` on `batch-build-log-kept-tests` (local only) |
| a68fda6d3fcd50241 | builder, sonnet | `a102496ba`, `5436f57c0`, `bb683a067`, `15389191a`, `c730fe6fe` on `batch-build-log-kept-r2` (pushed) |
| a88e1725a54623a25 | reviewer, sonnet (round 2) | none (read-only) |

Every commit of the local-only branches is an ancestor of `batch-build-log-kept-r2`, so nothing is lost if they go.
