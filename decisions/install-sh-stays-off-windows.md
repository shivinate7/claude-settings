# install.sh stays off Windows, install.ps1 is the Windows installer

## The ruling

`install.sh` does nothing on Windows. Under a MINGW, MSYS or CYGWIN `uname`, it exits 0 at its top with one line that names `install.ps1`, and it writes nothing. The SessionStart refresh hook does not call it there (owner ruling 2026-10-21).

Reason: the Mac/Linux installer ran on every Windows session start and landed the POSIX-only rm shim.

## The Windows update path (known choice, owner ruling 2026-10-21)

- The SessionStart pull is skipped at `settings.json:160`: the `-live` pin is a worktree, so its `.git` is a file, and the `[ -d "$d/.git" ]` test fails. It updates nothing.
- After a merge, `merge/install_from_main.sh` moves the pin, then runs `install.ps1` on MINGW (lines 165-174, the call at 169). `install.ps1` makes new links. It only creates a missing pin (`install.ps1:107-108`).
- Existing files in `~/.claude` update through the pin link.
- New files appear only after that `install.ps1` run, or a manual one.
- The post-merge hook exists only on a copy install (decision post-merge-hook-is-a-fallback). It re-copies files, and re-runs `install.ps1` when a pull changed it.

Kind: build
Plan: decisions/install-sh-stays-off-windows.md#the-ruling (all)
Home: install.sh
Home: settings.json
Home: install.ps1
