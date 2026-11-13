# A reinstall that misses the tip reruns at every prompt

**What.** `hooks/stale_install.py` reruns the installer at every prompt while the install record stays behind origin's tip, after a failed install, a lock wait, or a mirror kept on a local commit. Worst case: about 75 s per prompt, the 10 s origin read plus the 60 s installer limit plus the 5 s stop grace; typical is about 10-25 s.

**Where.** `hooks/stale_install.py`, `check()` and its call to `reinstall()`.

**Decision.** none.

**Retire.** After a reinstall that did not reach the tip, the hook skips the installer for that tip, for the rest of the session or for a bounded time. A stamp that the hook itself reads holds the skip. A case in `hooks/test_reinstall_stale.py` proves one installer run per tip.
