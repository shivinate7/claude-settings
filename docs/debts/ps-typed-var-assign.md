# The frozen-path guard misses a PowerShell variable set with a type prefix

**What.** `[string]$D = 'T'; Set-Content $D x`, `[string]$D='T'` and `[System.IO.FileInfo]$D = 'T'` set `$D` in PowerShell, but the resolver reads only a bare `$D` word, so the write to the frozen path `T` is allowed. The old resolver refused them (review round 3 of lane resolve-vars-quote-split, 2026-11-08 CST). A type prefix is a form Claude writes in normal PowerShell work.

**Where.** `hooks/guard_frozen.py`, `_resolve_into`, the PowerShell assignment arm (the word must be exactly `$D`).

**Decision.** `frozen-path-resolves-shell-vars` (the frozen-path check reads variables set earlier in the command).

**Retire.** A verdict case in `hooks/test_guard.py` for each of the three forms, red before the fix, green after: `hooks/test_guard.py`.
