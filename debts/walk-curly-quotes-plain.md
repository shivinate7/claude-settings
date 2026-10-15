# The quote walk reads curly quotes as plain text

- **What.** PowerShell can take the curly quotes U+2018 to U+201E as quote marks. The guard's quote walk reads them as plain text. A command with a curly quote can then hide a step inside what the walk reads as a quoted span, such as `echo 'abc’; git commit … >/dev/null; '`. Main and lane swn-pwsh-escape both allow it. Nobody checked how PowerShell reads these quotes.
- **Where.** `quote_advance` and `walk_quotes` in `hooks/guard_core.py`.
- **Decision.** None yet.
- **Retire.** A probe proves how PowerShell reads each curly quote. The walk reads them the same way or fails closed, with one case per quote.
