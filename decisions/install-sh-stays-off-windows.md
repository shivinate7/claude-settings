# install.sh stays off Windows, install.ps1 is the Windows installer

## The ruling

`install.sh` does nothing on Windows. Under a MINGW, MSYS or CYGWIN `uname`, it exits 0 at its top with one line that names `install.ps1`, and it writes nothing. The SessionStart refresh hook does not call it there (owner ruling 2026-10-21).

Reason: the Mac/Linux installer ran on every Windows session start and landed the POSIX-only rm shim.

Kind: build
Plan: decisions/install-sh-stays-off-windows.md#the-ruling (all)
Home: install.sh
Home: settings.json
Home: install.ps1
