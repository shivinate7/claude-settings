# The frozen-read check misses an in-place sed behind a wrapper

**What.** The frozen-read check reads a command's words by position. A `sed -i` behind a wrapper passes. The wrappers are `stdbuf -o0`, `flock`, `ionice`, `watch`, `busybox`, `su -c`, `parallel` and `chrt`. So the check does not refuse an in-place edit of a frozen file behind one. Claude could write one by mistake, but rarely.

**Where.** `hooks/guard_frozen.py`, the frozen-read check.

**Decision.** cull-guard-wrong-refusals (the guard cull), which names this limit.

**Retire.** Closed when a case in `hooks/test_guard.py` refuses a `sed -i` on a frozen file behind each wrapper named in What.
