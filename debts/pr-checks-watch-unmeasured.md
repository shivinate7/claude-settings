# The background checks watch is unmeasured

**What.** The guard still allows `gh pr checks --watch` in the background. Its API cost is
unmeasured. The guard also does not read a `gh run watch` wrapped in `bash -c`, `cmd /c` or
`pwsh -Command`.

**Where.** `hooks/guard_stream.py`, `gh_watches` and `waiter_verdict`.

**Decision.** ci-wait-reads-run-status (CI waits read the run status).

**Retire.** Count the calls of one `gh pr checks --watch` for 60 s with `GH_DEBUG=api`. If the
count is near the run watch's, refuse it the same way.
