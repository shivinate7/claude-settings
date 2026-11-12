# The text-read check denies a python heredoc that names gh

**What.** The text-read check denies a `python3 -c "..." <<\EOF` whose plain body names `gh`. The body is text, not a command, so the denial is a false alarm. Unmeasured how often Claude writes such a body.

**Where.** `hooks/guard_core.py`, about lines 1140, 970 and 1073.

**Decision.** cull-guard-wrong-refusals (the guard cull), which names this limit.

**Retire.** Closed when a case in `hooks/test_guard.py` allows a plain heredoc body that names `gh` under `python3 -c`.
