# Handoff: lane fast-forward-clean-start (2026-11-19 00:30 CST)

Session: session_013NEJL37QY2EjAqXYiuEe3b (lane, started by the Coordinator, session_013NEJL1gw6EdrSyvHkTUEx6).
Role: lane. It also took the Coordinator's added scope, lane `compact-refreshes-hooks`.

## Open PRs (read from GitHub at 00:27 CST Nov 19)

| PR | Branch | Head now | State | Head I handed in |
|---|---|---|---|---|
| #3141, a session fast-forwards its clean checkout at start | `fast-forward-clean-start` | `e9484864e5ec274dcb9e7ef76cc5ce92f2b6f1aa` | open, draft, mergeable_state dirty | `07d1af67675f71678ab4d3bee4494ff76236da90` |
| #3188, a cloud session that compacts refreshes its hooks | `compact-refreshes-hooks` | `befa11de6a2a8029d320abe2e9b8fcbcc6701b9e` | open, draft, mergeable_state unknown | `f9154aebe960020df5a0e3c67828a6eea96698a8` |

Both heads moved after my hand-in. I did not read why; a plain merge of main by the batch runner is the standing grant's route. Unread: their commits since the hand-in, and any review record or lane lint at the new heads.

## Done

- #3141 at `07d1af6767`: lane lint PASS. Review record posted at that head (round 1 reviewer sonnet FAIL, then fix check reviewer sonnet PASS, Guard or check: yes): https://github.com/shivinate7/claude-settings/pull/3141#issuecomment-6861024925. Handed to batch runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) marked "R67 express" on 2026-11-13 12:40 CST.
- #3188 at `f9154aebe9`: lane lint PASS. Review record at that head (round 1 reviewer haiku PASS, Guard or check: no): https://github.com/shivinate7/claude-settings/pull/3188#issuecomment-6861470910. Handed to runner 10 marked "R67 express" on 2026-11-13 12:31 CST.
- Behaviour built in #3141: at a `startup` SessionStart, after the one-ref refresh, `hooks/session_start.sh` runs `git merge --ff-only origin/<default>` in a clean checkout on the default branch that is behind, and prints one line. Every other case is a no-op plus one line, or no line.
- Behaviour built in #3188: `install.sh:1019`, the cloud refresh entry's matcher, is now `startup|resume|compact`; README rollout text; tests.
- Ruling c36 (advisor ruling, Oct 23, session-start fast-forward; Coordinator 09:54 CST and triage 10:00 CST, Nov 13) settles the shared-checkout question: keep as built.

## Unfinished

- Neither PR is merged. Neither was marked ready.
- #3188: four reviewer notes still to file as one note in `docs/debts/notes.md`: (1) `hooks/test_install_src.sh` 2266-2274, cloud_compact3, the run half passes vacuously when the refresh's curl fails; (2) README 116 and 157 conflict with decision `cloud-start-hooks-run-fresh` lines 23, 34, 36; (3) `install.sh` ~517, each compaction can now move a clean detached cloud checkout to origin/main mid-task; (4) loose wording at `install.sh` 1003 and README 289. A notes-only commit moves the head, so file it after the merge.
- #3141 known edges (not fixed, in `docs/debts/notes.md` line `ff-startup-merge-edges`, seven edges): unbounded merge and `index.lock` collision, assume-unchanged files read as "merge failed", a feature branch behind prints "not on main" at each start, an empty directory at an added path holds with the wrong reason, case-only renames on case-insensitive filesystems, newline in a path, the "pull before you read it" line after a refusal. Also bash 3.2 itself is unmeasured: the macOS draft run read it only at `07d1af6767`.
- The "or an owner prompt" part of ruling `fast-forward-clean-start` is not built; the hook runs on SessionStart only.

## Next step

Read each PR's live head, record and lane lint. If a head moved by a clean merge of main only, the standing grant ("Main merge into handed-in branches") says a clean merge needs no fix verifier. Otherwise a fix verifier and a new `merge --review-record` at the live head are owed. Then hand in again to the batch runner.

## Rules that cost time (for the next lane)

- `merge --review-record` takes a record only at the live head. A record comment must end with the line `CI: read live by merge --reviewed`, then a `---` line, then any text. Text between them makes the record unreadable to the tool.
- `merge --lane-lint` waits on the draft `lane-touched-tests` run at the head; it takes about 5 minutes after the run ends.
- macOS `/bin/sh` is bash 3.2: no `case` and no comment inside `$( )`.

## Refused acts

- Agents were refused `git worktree add` for a separate red checkout (hand-made-worktree guard); red runs ran in each agent's own worktree. `check_red_run.py` accepted them.
- No override line was printed to me. No owner act is open.

## Owner rulings I hold

- `fast-forward-clean-start` (owner 21:59 CST Nov 12), step `fast-forward-clean-start`.
- c36 (advisor ruling, Oct 23): the hook fast-forwards whichever tree holds main when it is on main with no tracked changes.
- R9 (owner 12:27 CST Nov 13, `roadmap/rulings/r9.json`): a guard or check change whose round 1 passes is done. Relayed by the Coordinator.
- R67 express: a fresh round 1 at the head, post its record, lane lint, hand to runner 10 (Coordinator 11:13 CST Nov 13).

## Agents (all finished; none running)

| Role | Model | Branch or worktree |
|---|---|---|
| test-author | haiku | `agent-ac0323f1cffa6c33b` (tests, then pushed to `fast-forward-clean-start`) |
| builder | sonnet | `agent-adcce611ab0824d7e`; later `agent-a3eccce1ab3c25d3d`, `agent-a2a432982974f1d35`, `agent-a590f5bc115e3d729`, `agent-a0b5f9ef72963f319` |
| builder | opus (round 3) | `agent-aed22cab635bd7507` |
| reviewers | haiku and sonnet | read-only; worktrees `agent-a2c842f46e33c34bb`, `agent-aae697c5b35ca7bd4`, `agent-a18183b26af74cfc4`, `agent-a58bfa3a079a33e62`, `agent-a8cf8e38ea972e42f`, `agent-a005bae2c305196d7`, `agent-ae40a854f94487cad`, `agent-a0ac11e5fb8ea88f2`, `agent-a298531547505af99`, `agent-a3b4108018279113e` |
| test-author | haiku | `agent-aa3662e00f63df1b7`, `agent-a850d0743c45a1532`, `agent-a591b74be3270430e`, `agent-a9b5f01d8cda0545e` (#3188 tests) |
| builder | sonnet | `agent-aaa8a5b895e91201f` (#3188 matcher) |
| record-writer | default | `agent-adfe5ce7021228592` (#3188 README and notes) |

Local lane worktree: `.claude/worktrees/fast-forward-clean-start`.
