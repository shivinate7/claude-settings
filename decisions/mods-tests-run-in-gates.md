# Mod tests run as the last step of the gates job

## The ruling

The mod tests (`*.test.mjs` and `*.test.js` under `mods/`) run as the last step of the existing
required `gates` job, on Linux. They do not run in a new job.

- It sets `shell: bash`. Its condition is `if: !cancelled() && needs.scope.outputs.mods == 'true'`.
- It captures `find mods` first: every `*.test.mjs` and `*.test.js` file except under `node_modules`.
  It fails if find fails (a missing `mods/` too) or lists no file. A silent empty run cannot pass.
- It loops over that list: `node "$f" || fail=1`. It ends with `exit "$fail"`. Every file runs. Any failure fails the step.
- It uses the runner's Node. It has no `setup-node` step.
- The scope flag `mods` is set in `.github/scripts/harness-scope.sh` for any path under `mods/`. The flag is in `ALL`, so push, schedule, dispatch, an unreadable diff and an unmapped path all run the step.
- `.github/stamp.json` and branch protection do not change. `gates` is already required.
- The step is last. A red mod test does not skip zizmor, the lints and the Python suites. `!cancelled()` lets it run after an earlier red step.

Reason: a red mod test must block a merge, and `gates` is already required. One CI run per batch.

Kind: process
Plan: decisions/mods-tests-run-in-gates.md#the-ruling (linux)
Home: .github/workflows/gates.yml

## Holes, named

Unverified: zizmor on the step (not installed here); whether `cancelled()` is true on a job timeout.
