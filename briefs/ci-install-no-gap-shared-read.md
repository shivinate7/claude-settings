# Brief: install-no-gap.test.ps1 reads redirected output with sharing (CI fix lane)

Repo: shivinate7/claude-settings, from current main plus lane PR #707 (branch claude/project-thread-auu2bj, head c6badc1): branch from that head, since #707 has not merged yet. One lane: builder (sonnet), then reviewer (sonnet). Follow-up from #707's report; serves c95 step 1.

## Task
install-no-gap.test.ps1 reads retry1's redirected stdout ($T1Out) with `[IO.File]::ReadAllText`, the same race #707 fixed in install-set.test.ps1 ("being used by another process"). Read it through one shared-read helper. If both test files now carry their own `Read-Shared`, move it to one home (a dot-sourced helper beside them, like testing/TrackedTree.ps1) and call it from both. Grep every other .ps1 test for `ReadAllText` on a file a child process wrote, and fix those too.

## Rulings
- building-one-home-per-capability; outcomes-tests-are-claims.

## Failure classes
- A shared helper that hides a missing file where a case needs text.

## Check that proves it done
A case red on main (held-open file read by the old reader throws), green on the branch, proven on a pointer-windows dispatch run (`gh workflow run` on the branch) if pwsh is not in the container. `python3 bin/ci-job gates --lint --base origin/main` passes.

## Report
At most 10 lines: PR (draft), head, red run, green run, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
