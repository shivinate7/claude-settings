# Question for the owner: a very long command can outrun the guard

- **What.** An odd count of `'` doubles guard time. A 6,001-word command takes about 15 to 32 s here, near or past the 20 s hook timeout. Then the call runs unjudged, which `gate-hooks-fail-closed` accepts.
- **Where.** The second reading in `split_segments` (`hooks/guard_core.py`) and the per-word path read in `hooks/guard_frozen.py`.
- **Decision.** `gate-hooks-fail-closed` (a missing gate refuses; a slow or crashed gate does not).
- **Retire.** The owner rules. Branch `guard-time-budget` holds a guard that refuses at its own 15 s deadline, with tests. Or a faster per-word read keeps such commands under the timeout.
