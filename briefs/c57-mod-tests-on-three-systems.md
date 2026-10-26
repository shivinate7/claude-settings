# c57: mods run their tests on all three systems in CI

Cloud build thread brief. Build advisor, Oct 26, against claude-settings main 3f71d6b.

## Why

In .github/workflows/gates.yml the "Mod tests" step and the plain-english-map skill tests run only
in the ubuntu-latest job. The windows-latest and shell-macos jobs skip them. Incident: decision-watch
called `which -a python3 python`, which exits non-zero on a Mac with no `python`; Linux CI was
green. Fix PR #580 (decision-watch finds python one name at a time).

## Task

Run the same mod-test step (and the skill tests beside it) in the Windows and macOS jobs, under the
same `mods` scope flag the ubuntu job uses. One step definition, no copied block: use a composite
action, a shared script, or a matrix, whichever fits gates.yml's current shape. Keep the jobs'
caps; if a job's cap is too short, raise that cap and say by how much.

## Failure classes

- The step runs but finds no tests on one OS (path or glob differs). Proof: the job log on each OS
  names the same test count.
- The scope flag skips the step on Windows or macOS when a mod changes. Proof: a PR touching a mod
  file runs the step on all three.
- Red proof: show one mod test that fails only on macOS (for example, revert #580's fix on a
  scratch branch, or a fixture that needs `python` on PATH), red in the macOS job, then green.

## Roles

Orchestrate: builder and fresh reviewer (it changes what a gate checks). Base: main. Note #580 is
open; if your red proof uses its fix, rebase on main after #580 merges. PR stops at green.

## Report (25 lines max)

Done, Deviations, Input Needed, Next. Per OS: the test count and the job's wall time before and after.
