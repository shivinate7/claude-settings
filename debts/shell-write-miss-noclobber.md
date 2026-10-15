# A noclobber redirect onto a frozen path is not read

- **What.** `echo x >| P` writes P, but `REDIRECT` reads only `>` and `>>`, so the word after it is `|P` and the write is not seen. Main missed it too. Found while probing lane cap-ask-data.
- **Where.** `REDIRECT` in `hooks/guard_core.py`, read by `writes_to` and `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** The reader takes `>|` as a redirect, and a test shows the write is refused.
