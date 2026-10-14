# A guard timing case can still fail on a busy runner

- **What.** The rm-var cases now bound a ratio to a baseline run in the same process (bound 3, eighth-size baseline), so a uniformly slow runner does not fail it. The baseline must span many clock ticks, because Windows CPU time moves in 15.6 ms steps. Two limits stay. The 2000-span case still uses a wall-clock bound (0.48-0.77 s against 2 s). The 64000 case catches only a heavy per-segment scan: that mutant measured 3.08-3.57 against the bound of 3. A ratio cannot see a slowdown that is the same at each size, so a linear slowdown of any size passes. The rm-var and session-log cases have no absolute bound, and no check measures the guard against the 60 s hook timeout.
- **Where.** The rm-var timing cases in `hooks/test_guard.py`.
- **Decision.** `gate-hooks-fail-closed` (the guard must finish inside its hook timeout).
- **Retire.** Convert the 2000-span case to the ratio bound, and a week of macOS and Windows runs shows no false red.
