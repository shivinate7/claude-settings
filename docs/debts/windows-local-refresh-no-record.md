# A Windows local session gets no mid-session stable refresh

**What.** `install.ps1` writes no install record, so `hooks/stale_install.py` finds none on a Windows local session and stays silent. A merge landed from another machine reaches that session only at its next start. The hook never prints a false "current". The gap is a missing refresh, not a wrong answer.

**Where.** `install.ps1` (no record writer); `hooks/stale_install.py` `check()` (a local session with no record prints nothing); `merge/install_from_main.sh` (on Windows it runs `install.ps1`).

**Decision.** merge-reinstalls-from-main (the pin follows the branch sessions install from). Scoped out by the coordinator, 11:34 CST Nov 15, lane stable-refresh-local.

**Retire.** `install.ps1` writes the same four-field record as `install.sh` (ref, sha, source, installer), and the hook stops a reinstall by a method that exists on Windows (`os.killpg` does not). A case on a Windows runner then shows a moved tip reinstalled once.
