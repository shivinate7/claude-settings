Added work for your current batch: Windows process churn. Roadmap step c22 (stop the Mac/Linux installer and rm shim running on Windows). Finish or park the lane you are in first; do not restart lanes already done. These lanes are small and urgent, so land them as soon as your current lane allows, in this same batch. If they cannot share a batch, open them as their own small batch that merges first. They fix existing code on a platform it was never meant for. No measuring; prove each fix with a test.

Why: on the owner's Windows machine (Git Bash, no admin), RAM climbs to about 98% over a day and only a reboot clears it. Kernel memory grows with every process start. The worst offender caught was the rm shim: 4 processes (sh, a forked sh, the WindowsApps python3 alias, the real python) on every rm -rf.

Checked at 5584d1b:
- The settings.json SessionStart hook (startup|resume) runs `bash "$d/install.sh"` whenever bash exists, so the Mac/Linux installer runs on Windows at every session start.
- landed-dirs.txt includes bin, so it lands bin/rm, whose header says "Posix only; install.ps1 does not land this file."
- install.sh (near line 600) adds ~/.claude/bin to PATH in ~/.bashrc, putting the shim first in Claude Code's shells. install.sh has no Windows check.
- bin/rm calls bare python3 (the WindowsApps alias on Windows, which starts a second python) and builds its Python with $(cat <<'PYEOF'), one more fork.

Lane W1, the installer stays off Windows. The SessionStart hook skips install.sh when uname -s is MINGW*, MSYS* or CYGWIN*, and install.sh exits 0 at its top on those, naming install.ps1 as the Windows installer. Test both. Record the ruling in place under decisions/ (one ruling, a one-line reason).

Lane W2, the rm shim. On MINGW, MSYS or CYGWIN, exec the real rm at once, before any python. Elsewhere, find Python the way the hooks do (python3 then python, skip WindowsApps), and pass the Python on stdin with a here-doc instead of $(cat). Mac and Linux protection stays exactly as it is. Test the Windows exec path, the WindowsApps skip, and the existing refusal cases.

Lane W3, ci_wake's pre-filter. Tighten the PostToolUse shell pre-filter from any "ready" to the phrase gh pr ready, so other commands start no python. The watch itself, its deadline and asyncRewake stay.

Overlap with your current lanes: W1 and W3 edit settings.json, which your 'if' filter lane also edits. Do them in one pass on settings.json, or rebase whichever lands second; keep both sets of changes.

In your report, add:
- Per W lane: what changed and the test that proves it.
- A checklist the owner runs on the Windows machine after this merges and is pulled, no admin needed and nothing scripted: delete ~/.claude/bin/rm; remove the "# claude-settings: ~/.claude/bin on PATH" block from ~/.bashrc; check ~/.claude/claude-settings-install.log for install.sh runs; and check whether install.sh replaced ~/.claude/settings.json or a landed folder with something install.ps1 would not have made, and how to put it back.
