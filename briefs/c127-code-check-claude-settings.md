# Brief: c127 part 1, one shared code-check action, adopted by claude-settings first

Repo: shivinate7/claude-settings, from main 43d9af20 (batch #698). One lane: builder (sonnet), then reviewer (sonnet). Plan: roadmap step c127 note and https://claude.ai/artifact/K4ixuAMi4ycpBvgm2x4k3H (survey and pick).

## Task
1. A composite action `actions/code-check` with pinned tool versions, CI only. Per language, three layers (type check, bug lint, formatter), or a one-line reason in the standard's table for each skipped layer. The action fails on a repo language with no row.
   - Python: Ruff with bug rules (today `pipx run ruff==0.17.1 check .` in gates.yml, rules in ruff.toml), and mypy strict over a per-repo list of modules that only grows.
   - Shell: ShellCheck. TS: `tsc --noEmit` where a tsconfig exists.
   - Formatters wait for o2 (one layout); their rows say "after o2" and the action does not run them yet.
2. The standard's table: one home (a doc or json beside the action), with a gold-standard column, read by the action. 
3. claude-settings adopts it in gates.yml in place of its Ruff step. Start the mypy list with at least one module that passes strict today, and say which.
Child repos are out of scope (each needs shiv's word). c129 also edits gates.yml; keep your edit to the lint step.

## Rulings
- building-one-home-per-capability; verification-newest-that-passes (pin the newest that passes, read its changelog).
- c127 note: skip stylelint and sqlfluff; no SwiftLint; actionlint only after an incident.

## Failure classes
- A list that can shrink without a red check.
- A language in the repo with no row that the action passes silently.

## Check that proves it done
Tests of the action's language-row logic: red on main (no action), green on the branch, including a planted language with no row (red) and a planted mypy error in a listed module (red). `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 15 lines: PR (draft), head, red runs, green runs, review verdict, the starting mypy list. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
