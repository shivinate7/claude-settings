# A cloud checkout detached at main's tip reads as off main

**What.** hooks/session_start.sh counts a detached checkout as on main only when HEAD equals local `refs/heads/main`. A cloud session's local `main` stays at an older commit, so a checkout detached at origin/main's tip prints "is on a detached HEAD, not main" at every start and skips the freshness check. Seen at the start of the lane session for #841: local `main` was f1f7fa92 and HEAD was 53536ea7, main's tip.

**Where.** hooks/session_start.sh, the pointer branch check. install.sh moves a clean, detached cloud checkout to origin/main, which makes this case the usual one.

**Decision.** session-tiers, the session shapes and the cloud merge role.

**Retire.** session_start.sh also counts HEAD equal to `refs/remotes/origin/main` as on main. A test in hooks/test_install_src.sh starts with a stale local `main` and HEAD at origin/main, and shows no "not main" line.
