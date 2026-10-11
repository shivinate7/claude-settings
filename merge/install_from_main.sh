#!/usr/bin/env bash
# afterMerge helper: run install.sh from the worktree that holds refs/heads/main, never the
# caller's own tree, so ~/.claude links point at main after a merge.
# Limit: install.sh is not for Windows. On MINGW, MSYS or CYGWIN this prints a pointer to
# install.ps1 and exits 0.
case "$(uname)" in MINGW*|MSYS*|CYGWIN*) echo "Windows: run install.ps1 by hand; install.sh not run."; exit 0 ;; esac
main=$(git worktree list --porcelain | awk '/^worktree /{p=substr($0,10)} $0=="branch refs/heads/main"{print p; exit}')
if [ -z "$main" ]; then echo "No worktree holds main; install.sh not run."; exit 0; fi
echo "Installing from $main"
bash "$main/install.sh"
