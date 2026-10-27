# Brief: install-set.test.ps1 reads a run's output with sharing (CI fix lane)

Repo: shivinate7/claude-settings, from current main. One lane: builder (sonnet), then reviewer (sonnet). Follow-up found by the build advisor; serves c95 step 1 (a full run where red means broken).

## Task
pointer-windows failed on batch #704 (run 40548200063, job 122344567819) in install-set.test.ps1, case lock1: `Get-RunText` reads a run's .out.txt with `[IO.File]::ReadAllText`, which throws "being used by another process" while another process still holds that file open for write. The same file has `Read-Shared` (read with ReadWrite and Delete sharing). Make `Get-RunText` read through `Read-Shared`. Check whether any other reader in install-set.test.ps1 or install.test.ps1 has the same pattern, and fix those too. Say which process still held the file, if the log or code shows it; if not, say unknown.

## Rulings
- building-one-home-per-capability (one shared-read helper); outcomes-tests-are-claims (fix the reader, never skip the case).

## Failure classes
- A reader that hides a real missing output: `Read-Shared` must still fail the case when the file is absent or empty where the case needs text.

## Check that proves it done
A small PowerShell case red on main: a file held open for write by another handle, read by `Get-RunText`, throws; green on the branch. If pwsh is not in the container, say so and prove it on the branch's pointer-windows CI run.

## Report
At most 10 lines: PR (draft), head, red run, green run, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
