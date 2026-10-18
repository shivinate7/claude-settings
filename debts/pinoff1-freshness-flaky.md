# Pin freshness case fails at random on Windows

- **What.** Case pinoff1 expected one freshness line and got none, on a commit that changed only the records page (run 39080117103). The same tree passed twice, so the case is flaky and can block a merge.
- **Where.** `pinoff1` in `hooks/test_install_src.sh`, which runs the session-start freshness check in a pinned worktree, in the gates-windows job.
- **Decision.** none
- **Retire.** Find what the freshness line depends on in that fixture (fetch time, clock or clone state) and pin it; the case passes on repeat Windows runs.
