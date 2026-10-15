# The guard allows a shell call inside a python heredoc

- **What.** `python - <<EOF` with a body that calls `os.system("git stash")` is allowed. The guard does not read a python body for shell calls. Case B19 pinned this gap as allowed; lane cut-tests-guard cut the pin.
- **Where.** The heredoc reading in `hooks/guard_core.py` and `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (a hole pin becomes a debt).
- **Retire.** The guard reads `os.system` and `subprocess` calls in a python heredoc, with one deny case for each.
