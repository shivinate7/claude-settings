# A very long command passes the guard by timing out

- **What.** An odd count of `'` doubles guard time: 6,001 words take 31.8 s against the 20 s hook timeout (main 15.6 s). A timed-out hook does not block the call, so such a command runs unjudged.
- **Where.** The second reading in `split_segments` (`hooks/guard_core.py`), the per-word path read in `hooks/guard_frozen.py`, and the guard rows in `settings.json`, which set no `onFailure`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** The guard rows set `"onFailure": "block"`, so a timeout fails closed. A guard test with an odd `'` count over 6,000 words is judged or denied, never let through.
