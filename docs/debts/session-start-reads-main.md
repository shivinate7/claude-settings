# The session-start freshness check reads main, not the install record's ref

**What.** The freshness check in `hooks/session_start.sh` reads literal `origin/main` and skips only `claude-settings.cloudMirror` clones. Roadmap step R42 part 2 act 2 makes the installers read a `stable` branch. Then the check must read the install record's ref, or the two checks disagree for a non-mirror cloud checkout.

**Where.** `hooks/session_start.sh`, the freshness check that prints "commits behind origin/main".

**Decision.** none.

**Retire.** The check reads the install record's ref. A session_start test where the record's ref is not `main` shows the check reads that ref: a case in `hooks/test_session_start.py`.
