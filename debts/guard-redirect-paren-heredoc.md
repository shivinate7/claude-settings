# Three command shapes hide a kill from the guard

- **What.** These hide a refused command, and main allows them too: a leading redirect before the command word (`2>/dev/null pkill foo`), and `)#` that opens no comment. A third is a heredoc header line that ends in an open quote.
- **Where.** `split_segments` and `resolve_command` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** The resolver skips leading redirects, and the reader treats `)#` as bash does. Kill-family cases for all three shapes deny.
