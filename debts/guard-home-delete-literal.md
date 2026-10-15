# The guard allows a delete of another user's home folder

- **What.** `rm -rf /home/x` and `rd /s /q C:\Users\x` are allowed. The delete rule guards only the session user's own home path. Two pins of this gap were cut in lane cut-tests-guard.
- **Where.** The delete rule in `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (a hole pin becomes a debt).
- **Retire.** A named incident or measured risk shows the need. Then a recursive delete of a folder directly under `/home` or `C:\Users` is denied, with one case per form.
