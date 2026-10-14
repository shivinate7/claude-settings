# A very long command nears the guard's timeout

- **What.** A command of about 6,000 words with an odd count of `'` takes about 18 s, near the 20 s hook timeout. What happens at the timeout is untested.
- **Where.** The per-word path read in `hooks/guard_frozen.py`, and the second reading in `split_segments`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Cache the per-word path read, and test that a timeout fails closed. A guard test judges a 6,000-word command in under 5 s.
