# PowerShell smart quotes and block comments hide a write on main

- **What.** On main, a frozen path in smart quotes (U+201C, U+201D, U+2018, U+2019) and a `<# note #> Set-Content P` are read as plain text or as no command, so the write is allowed. Found in review of lane cap-ask-fix. This lane fails closed on both only where it would read text as data. A smart-quoted path with no printer or message text around it is still allowed.
- **Where.** `_shell_write_hit` and `_scan` in `hooks/guard_frozen.py`; `split_segments` in `hooks/guard_core.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader. It does not name these forms.
- **Retire.** The reader reads smart quotes as quotes and drops `<# #>` comments in PowerShell text, and a test shows each write refused.
