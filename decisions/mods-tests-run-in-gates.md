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

Debts: `mods-check-mjs-skipped` (a red `check.mjs` passes CI), `mods-tests-glob-too-narrow` (nested and `*.test.js` tests never run), `mods-session-board-timer-margins` (two real-timer margins are unproven on a slow runner), `mods-node-version-unpinned` (the runner's Node version is unknown), `mods-step-order-unpinned` (no test pins that this step is last), `mods-linux-proof-pending` (the first CI run on Linux is the real proof), `harness-scope-mods-flag-missing` (STEP_FLAGS lacks mods). `harness-scope-pipe-regex-quotes` (the pipe regex ignores quotes and comments). `harness-scope-line5-too-long` (a line in the scope script is about 140 characters). `process-record-dead-plan-line` (this record keeps a Plan line that no check reads).

## Unverified

- zizmor on the new step. zizmor is not installed here.
- Whether `cancelled()` is true on a job timeout. The job is red either way.

Kind: process
Plan: decisions/mods-tests-run-in-gates.md#the-ruling (linux)
Home: .github/workflows/gates.yml
