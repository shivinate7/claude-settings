# A failed skill copy still exits 0

- **What.** If `Install-Dir` cannot replace a skill folder, the run does not retry it and exits 0. Main does the same. Also, the log can say `settings.json=kept` after a retry recovered it.
- **Where.** `install.ps1`: `Install-Dir`, `Resolve-Failures`, and `Write-InstallLog` before the settings retry.
- **Decision.** `install-hooks-whole` (an install never shows a session a half-copied hook).
- **Retire.** A failed skill folder joins the retry list and makes the run exit non-zero. The log line is written after the retry.
