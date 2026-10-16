# Tail arguments are not checked

- **What.** `harmless_tail` takes any arguments to `echo` and `Write-Host`. It checks the arguments of `tail`, `head` and `Out-Null`. `UNSAFE_TEXT` does not flag a PowerShell `(...)` subexpression. So `<ask>; Write-Host (Remove-Item x)` counts the tail as harmless and asks alone. Measured: 1 of 2 steps is harmless. Unmeasured: whether another rule judges the `Remove-Item` call.
- **Where.** `harmless_tail` and `UNSAFE_TEXT` in `hooks/guard.py`.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** The tail check reads the arguments of `echo` and `Write-Host`, and a chain with a command or a subexpression in them denies. A row in `hooks/test_guard.py` shows `<ask>; Write-Host (Remove-Item x)` denies.
