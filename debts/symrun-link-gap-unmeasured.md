# The symrun window check is unmeasured on the link route

- **What.** The symrun case wants at least one mixed-id window during run 2. The link route's gap is shorter than the copy route's gap, and nobody has measured it. On a loaded runner the reader can miss it and the case goes red.
- **Where.** `install-no-gap.test.ps1`, the symrun window check; the link swap in `install.ps1`.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** CI shows the link route at least once with a window seen. If the check flakes, run 2 is retried once when no window is seen.
