# c69: a new shared lint module never breaks test fixtures; a lane can run a whole gates job

Cloud build thread brief. Build advisor (3), Oct 26. Base: main after #615 (o2, one layout for
every repo) merges; the dispatcher names the commit. Never rebase onto main after review. Push
roadmap edits to the branch only; only "Triage the roadmap (3)" republishes the roadmap page.

## Finding

o2 lost three CI cycles to test fixtures that copy a hand-picked list of lint/ files into a temp
tree (lint/test_check_silent_undo.py, actions/ruling-kind/test_action.sh, and others). Each new
shared module breaks every such fixture, and the gates job finds them one per run. The lane's
local check list also skipped multi-line `run:` steps in .github/workflows/gates.yml.

## Task, two parts in order

(a) The cause. Find every test that builds a temp tree from a list of repo files (grep for
copies of lint/, hooks/, actions/ into temp dirs, in Python, shell and PowerShell). Give them one
helper per language that copies what git tracks under the named folders (git ls-files), so no
fixture lists files. Red first: add a dummy shared module that an existing lint file imports, show
the old fixtures fail, then green with the helper. Remove the dummy before you send.

(b) A `bin/` command that runs every step of a named job in gates.yml locally, each through
`verdict`, multi-line `run:` steps included, and prints one verdict per step. A step whose tool
is missing reads "unknown (tool missing)", never pass. Name it in agents/builder.md as the check a
lane runs before it sends a head that touches lint/, hooks/ or actions/.

## Fences

- Never weaken, skip or narrow a test. A fixture keeps every case it has.
- A step that uses `uses:` (an action) is listed as "not run locally", with the reason.
- Windows suites (PowerShell) get the same helper if they copy file lists; prove them through a
  gates.yml dispatch run on the branch.

## Failure classes and proof

- The dummy-module red run is the red proof; keep its output in the report as a verdict line.
- Changes test harness behaviour and the builder agent: a fresh Sonnet reviewer reads the diff.
- Run the new bin/ command on the gates job itself as the green proof.

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (3)". Do not merge, and do not rebase onto main. No question for
shiv: park any in the PR body.
