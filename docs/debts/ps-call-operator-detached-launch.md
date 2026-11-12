# A PowerShell call operator in braces is refused as a detached launch

**What.** On main, a PowerShell call operator inside braces is denied as a detached launch, as in `if ($true) { & dotnet build }` or `Get-ChildItem | ForEach-Object { & dotnet build }`. That is normal PowerShell, so Claude hits this false alarm in normal work, and it also hid the quote-before-call test rows of `guard-interpreter-body-git` (the interpreter-body guard step) that the lane dropped.

**Where.** `hooks/guard_kill.py`, function `bare_background_hit` (the reader of background jobs). It treats any `&` token after the command word as a background job, so the `&` after `{` counts. Found in review round 2 of that step.

**Decision.** `detached-launch-refused` (the detached-launch rule: it refuses a process that starts and detaches from the session).

**Retire.** Read an `&` followed by a command word or a parenthesized expression as a call operator, not a background job. Add to `tests/guard/s08727-push-delete.py` the quote-before-call rows: a quote inside a string before the `&`, and a lone apostrophe in text before the call. Add an allow case for each form in What. Each case is red before the fix and green after: `hooks/test_guard.py`.
