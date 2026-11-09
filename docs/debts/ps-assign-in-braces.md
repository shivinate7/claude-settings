# The resolver misses a PowerShell assignment inside braces

**What.** A PowerShell assignment inside braces is not read, so a write to a frozen path `T` through that variable is allowed. The old resolver refused each form below (review round 3 of lane resolve-vars-quote-split, 2026-11-09 CST). Claude writes braces like these in normal PowerShell work.

- `try { $p='T'; Set-Content $p x } catch {}`
- `@('a') | ForEach-Object { $p='T'; Set-Content $p x }`
- `if ($a) { x } else { $p='T'; Set-Content $p y }`
- `if($true){$p = 'T'; Set-Content $p y}`
- `foreach($f in 'a'){$p='T'; Set-Content $p y}`
- `function f{$p = 'T'; Set-Content $p y}`
- `& {$p="T"; Set-Content $p y}`

The spaced forms `try { $p = 'T' ...}` and `if ($true) { $p='T' ...}` still refuse.

**Where.** `hooks/guard_frozen.py`: `_WORD_STOP` has no `{`, and `_COMMAND_STARTERS` has no `try`, `catch`, `finally`, `ForEach-Object` or `}` before `else`. An unspaced `$D=v` is read only at a statement start, and `$D = v` needs the whole word `$D`.

**Decision.** `frozen-path-resolves-shell-vars` (the frozen-path check reads variables set earlier in the command).

**Retire.** A verdict case in `hooks/test_guard.py` for each form, red before the fix, green after: `hooks/test_guard.py`.
