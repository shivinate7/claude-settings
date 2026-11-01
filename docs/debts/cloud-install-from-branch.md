# A cloud install can take its files from a checkout's branch

**What.** In a cloud start or resume, install.sh takes the session's own checkout as its source. The cloud own-checkout block moves the checkout to origin/main only when it is clean, detached, and at a commit main holds. Otherwise the install takes settings, hooks and CLAUDE.md from the checkout's branch, with a warning only. Incident (coordinator, 2026-11-01 00:11 CDT): a resume installed from a merged session branch 102 commits behind main, with 2 merge allow rules where main has 4.

**Where.** install.sh, the source pick and the cloud own-checkout block.

**Decision.** merge-reinstalls-from-main (links that follow a checked-out branch put unreviewed or stale hooks live).

**Retire.** A cloud install from a checkout on an old merged branch, or on a branch with unmerged commits, installs main's files and leaves the checkout's branch and changes as they are. A test proves it red, then green.
