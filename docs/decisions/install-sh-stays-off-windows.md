# install.sh stays off Windows, install.ps1 is the Windows installer

## The ruling

`install.sh` does nothing on Windows. Under a MINGW, MSYS or CYGWIN `uname`, it exits 0 at its top with one line that names `install.ps1`, and it writes nothing. The SessionStart refresh hook does not call it there (owner ruling 2026-10-21).

Reason: the Mac/Linux installer ran on every Windows session start and landed the POSIX-only rm shim.

## The Windows update path (known choice, owner ruling 2026-10-21)

- The SessionStart refresh in `settings.json` runs on Windows too, in Git Bash. It moves local main to origin/main by fast-forward only, then, when the pin is not at main, runs `merge/install_from_main.sh`, which runs `install.ps1` there and never `install.sh`.
- After a merge, `merge/install_from_main.sh` moves the pin, then runs `install.ps1` on MINGW (its `uname` case at the end). `install.ps1` makes new links. It only creates a missing pin (its block for decision merge-reinstalls-from-main).
- Existing files in `~/.claude` update through the pin link.
- New files appear only after that `install.ps1` run, or a manual one.
- The post-merge hook exists only on a copy install (decision post-merge-hook-is-a-fallback). It re-copies files, and re-runs `install.ps1` when a pull changed it.

Kind: build
Plan: docs/decisions/install-sh-stays-off-windows.md#the-ruling (all)
Home: install.sh
Home: settings.json
Home: install.ps1
