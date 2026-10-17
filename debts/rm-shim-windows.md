# The rm shim has no Windows half

- **What.** `install.ps1` lands no `rm` shim, and `bin/rm` is posix only.
- **Where.** `install.ps1`, `landed-dirs.txt`.
- **Decision.** `rm-path-wrapper` (an rm shim on PATH, active only in Claude sessions).
- **Retire.** A Windows shim lands, with a fixture suite in the Windows jobs and an entry in `REQUIRED` in `lint/test_windows_split.py`.
