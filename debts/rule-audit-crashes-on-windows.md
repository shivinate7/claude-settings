# Rule audit crashes on Windows

- **What.** `lint/rule_audit.py` crashes on default Windows at line 212, reached from the per-row loop at line 457. The crash comes after the anchor checks, so the pin compare at line 475 never runs. On default Windows the pin goes unchecked.
- **Where.** `lint/rule_audit.py`. The cause is `subprocess.run` at lines 205-206, which decodes node output as cp1252.
- **Decision.** `debts-have-their-own-store` (where debts live). It names this crash as its fourth hole.
- **Retire.** Lane win-defects (f256c4a, on origin/win-defects) passes `encoding="utf-8"` to that `subprocess.run` call. Then the audit reaches the pin compare on Windows.
