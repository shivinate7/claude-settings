# The faster undo scan flags lines after a CR or NUL

- **What.** The scan reads `git log -p` as text. A lone CR or a NUL inside a changed line splits it, so later lines of that commit count as lost. That is a false alarm, never a false clear.
- **Where.** `git()`, `changed()` and the commit split in `lint/check_silent_undo.py`.
- **Decision.** `silent-undo-check-design` (how the check finds a merge that drops lines).
- **Retire.** Read the log as bytes, split on the NUL commit mark only, and check each sha is 40 hex digits. Probes with a CR-only file and a NUL text line match the old scan.
