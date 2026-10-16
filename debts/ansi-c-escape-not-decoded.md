# The guard does not decode escapes inside ANSI-C quotes

- **What.** Lane cap-ask-hole decodes a plain `$'path'` word for the frozen and model-cap checks. An escape inside the quotes, such as `\x2f` or an octal escape, stays as text. A protected path spelled with escapes can still pass those checks.
- **Where.** `_unquoted` in `hooks/guard_frozen.py`.
- **Decision.** None yet.
- **Retire.** `_unquoted` decodes the bash escapes of `$'...'`, with one deny case each for a hex and an octal spelling.
