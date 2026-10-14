# Mod tests run as the last step of the gates job

## The question

Where do the mod tests (`mods/*/*.test.mjs`) run in CI, so that a red mod test blocks a merge?

## The ruling

Merge session, 2026-10-13, 13:16 CDT. The mod tests run as the last step of the existing required `gates` job, on Linux. They do not run in a new job.

The step has these traits:

- It sets `shell: bash`.
- Its condition is `if: !cancelled() && needs.scope.outputs.mods == 'true'`.
- It loops over `mods/*/*.test.mjs`. For each file, it runs `node "$f" || fail=1`.
- It ends with `exit "$fail"`. Every file runs. Any failure fails the step.
- It uses the runner's Node. It has no `setup-node` step.

A new scope flag, `mods`, is set in `.github/scripts/harness-scope.sh` for any path under `mods/`. The flag is in `ALL`, so push, schedule, dispatch, an unreadable diff and an unmapped path all run the step.

`.github/stamp.json` and branch protection do not change. `gates` is already a required check.

The step is last. A red mod test therefore does not skip the other steps: zizmor, the lints and the Python suites. The `!cancelled()` condition lets the step run after an earlier red step.

## Why

- A red mod test must block a merge. `gates` is already required, so no branch protection change is needed.
- One CI run per batch. A hidden result costs a second run.

## Evidence

- Red proof, per the merge session ruling: the step's exact command, run locally. With one plain-diff case broken, it exits 1. On the real files, it exits 0.
- No CI red run exists for the step.
- About 200 mod cases never ran in CI before this change.
- The test-author wrote the pins red first, in `lint/test_harness_scope.py` and `lint/test_windows_split.py`.

## Review rounds

- Round 1 passed. Round 2 passed. No blocker was found.
- Both rounds ran on Sonnet.

## Holes, named

1. Cause: `mods/plain-diff/check.mjs` is a self-check script, and the glob skips it. Effect: a red `check.mjs` passes CI. Fix: rename it to `*.test.mjs`, or decide that it is out of scope.
2. Cause: the glob reaches only root-level `mods/<name>/*.test.mjs`. Effect: a test in `mods/<name>/tests/`, or named `*.test.js`, never runs, with no signal. Fix: widen the glob.
3. Cause: `mods/session-board/session-board.test.mjs` has two real-timer margins, about lines 709-718 and 928-940. Each is `within(200)` against a 100 ms grace. Effect: both margins are unproven on a slow runner. Fix: none named.
4. Cause: the runner's Node version is unknown. The tests need `register` from `node:module`, which needs Node 20.6 or later. Effect: an older Node cannot run them. Fix: read the version in the step, or set it.
5. Cause: no test pins that the step is last. Effect: a step added after it is skipped when a mod test fails. The job stays red, so the verdict is right. Fix: none named.
6. Cause: Claude Code's worktree isolation refused the builder's `wsl` command. The refusal text said the command "cannot be shown not to run git". The claude-settings guard was not the source: it had no WSL rule before commit eee2f72 (lane wsl-test-list). Decision `wsl-allow-list` (WSL command allow list) now sets that rule. The builder ran the mod tests on Windows only. The mod tests ran on Linux only through the owner's own terminal. That run was WSL: plain-diff 72 of 72, session-board 119 of 119, Node v22.23.1. Effect: those runs are not CI runs. The first CI run on Linux is the real proof. Fix: re-point a red Linux test, never skip it.
7. Cause, minor: `lint/test_harness_scope.py` lines 215-217 hold the stale comment "ALL stays as it is". `STEP_FLAGS` (line 24) lacks `mods`. The pipe regex in `mods_step_problems` ignores quotes and comments. `.github/scripts/harness-scope.sh` line 5 is about 140 characters long. Effect: the comment misleads a reader, and the regex can misread a pipe inside a quote or comment. Fix: correct the comment, add `mods` to `STEP_FLAGS`, make the regex skip quotes and comments, and wrap line 5.

## Unverified

- zizmor on the new step. zizmor is not installed here.
- Whether `cancelled()` is true on a job timeout. The job is red either way.

Kind: process
Home: .github/workflows/gates.yml
