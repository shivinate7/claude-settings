# A guard timing case can still fail on a busy runner

- **What.** The rm-var cases now bound a ratio to a baseline run in the same process (bound 3, eighth-size baseline), so runner speed cancels out. Two limits stay. The 2000-span case still uses a wall-clock bound (0.48-0.77 s against 2 s). The 64000 case catches only a heavy per-segment scan: that mutant measured 3.08-3.57 against the bound of 3.
- **Where.** The rm-var timing cases in `hooks/test_guard.py`.
- **Decision.** `rm-on-a-variable-needs-a-guard`.
- **Retire.** Convert the 2000-span case to the ratio bound, and a week of macOS and Windows runs shows no false red.
