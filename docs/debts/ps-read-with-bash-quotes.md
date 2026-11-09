# The resolver reads PowerShell text with bash quoting

**What.** In PowerShell text the resolver pairs double quotes by bash rules: a `\` before `"` or a newline escapes it. PowerShell's escape is the backtick, so a path ending in `\` is plain text. A wrong pairing hides a later `$p = "T"` (T = a frozen path), and the write is allowed. The old resolver never paired double quotes in PowerShell text, so it denied each form below (review round 3 of lane resolve-vars-quote-split, 2026-11-09 CST). Forms: `$dir = "C:\x\"` then `$p = "T"` then `Set-Content $p y`. `cd C:\x\` then `$p = "T"`. `Write-Host "path is x\"; $D = "T"; Set-Content $D y`. `$a = "x`"y"; $p = "T"; ...`. `& {$p="T"; Set-Content $p y}`. A trailing-backslash Windows path is ordinary PowerShell, so Claude can write it.

**Where.** `hooks/guard_frozen.py`, `_dq_end`, `_read_word` and the PowerShell `$p=v` arm of `_resolve_into`.

**Decision.** `frozen-path-resolves-shell-vars` (the frozen-path check reads variables set earlier in the command).

**Retire.** A verdict case in `hooks/test_guard.py` for each form, red before the fix, green after: `hooks/test_guard.py`.
