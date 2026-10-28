# c172-lint-needs-base

Status: green, reviewed. Draft PR #758, head 5f875487.
Pick: `--lint` with no `--base` defaults to origin/main (the smaller fix; it matches CI). If origin/main does not resolve, it prints one unknown line that names the skipped pull-request steps, and exits 2.
Gates: unit tests PASS (red on old code: 3 failures), `ci-job gates --lint --base origin/main` PASS, silent-undo strict PASS.
Review: round 1 APPROVE (reviewer opus); builder opus. No net-value test, since it closed in round 1.
Notes for the orchestrator. They are outside this step's files, so they were not fixed here:
- skills/project-ops/templates/brief.md:24 still tells lanes to run `bin/ste-changed origin/main` separately, because the mode once skipped the STE step. ci-job now runs that step. The extra run is harmless and redundant. It needs a follow-up rewrite.
- A plain `ci-job gates` (no --lint, no base) still skips pull-request steps and can exit 0. This is out of scope for c172.
- In a repo whose default branch is not main, `--lint` with no base reads unknown (exit 2) and asks for --base. That is honest, not a false pass.
