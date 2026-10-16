# The silent-write check re-walks each segment per redirect

- **What.** Unmeasured. `discards_output` calls `unquoted_at` once for each redirect match. Each call walks the text from index 0 with `walk_quotes`. So k matches cost k walks of the whole segment. A segment with `$(` or a backtick and a redirect also runs `_substitutions` and a second round of walks. `tail_discards` runs `discards_output` on the pipe tail, so the cost repeats there.
- **Where.** `discards_output`, `unquoted_at` and `tail_discards` in `hooks/guard.py` (lines 429-472); `walk_quotes` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `unquoted_at` reads every redirect's quote state in one walk. A timing check over a long segment with many redirects shows linear growth.
