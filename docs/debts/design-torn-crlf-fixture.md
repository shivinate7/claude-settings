# A text-mode fixture write broke the Windows check

- **What.** The design-torn fixture in hooks/test_guard.py (a test clone whose tip has a missing tree) wrote its commit text in text mode through `git hash-object -w --stdin`. On Windows, text mode writes CRLF, and git 2.56's fsck refused the commit ("badTreeSha1"). The Windows CI job (checks-windows-guard) caught it, and integration batch 64 dropped PR #1181 (lane design-branch-delete).
- **Where.** hooks/test_guard.py, the design-torn fixture. Commit ffc6fb176 (the fix that writes the fixture's text as bytes) cleared it.
- Fix: none — the Windows CI job refuses the bad object before any merge, so the harm is one dropped batch lane. A scanner for text-mode git object writes in test fixtures costs more than that. Until: 2026-11-21.
- **Decision.** design-branch-delete-guard (the ruling that a branch delete keeps its design file).
- **Retire.** none. No check closes it.
