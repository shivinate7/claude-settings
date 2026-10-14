# A guard timing case can still fail on a busy runner

- **What.** The rm-var cases now bound a ratio to a baseline run in the same process (bound 3, eighth-size baseline), so a uniformly slow runner does not fail it. The baseline must span many clock ticks, because Windows CPU time moves in 15.6 ms steps. Two limits stay. The 2000-span case still uses a wall-clock bound (0.48-0.77 s against 2 s). The 64000 case catches only a heavy per-segment scan: that mutant measured 3.08-3.57 against the bound of 3.
- **Where.** The rm-var timing cases in `hooks/test_guard.py`.
- **Decision.** `gate-hooks-fail-closed` (the guard must finish inside its hook timeout).
- **Retire.** Convert the 2000-span case to the ratio bound, and a week of macOS and Windows runs shows no false red.
