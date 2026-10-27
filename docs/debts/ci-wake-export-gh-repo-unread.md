# ci_wake reads no exported GH_REPO

- **What.** ci_wake reads GH_REPO only as a command prefix. export GH_REPO=... and PowerShell $env:GH_REPO=... before gh pr ready are not read, so the watch says nothing. This is the same as before the false-alarm fix.
- **Where.** hooks/ci_wake.py, the gh pr ready parse.
- **Decision.** `ci-wait-reads-run-status` (the CI wait reads the run's status).
- **Retire.** Read GH_REPO from the hook's environment when no flag or prefix names a repo. Check: a case with GH_REPO in the env.
