# Rule audit crashes on Windows

- **What.** `lint/rule_audit.py` crashes on Windows. The subprocess output decodes as cp1252, and the audit stops before it checks anchors.
- **Where.** `lint/rule_audit.py`, the `.mjs` test-listing path at line 212.
- **Decision.** `debts-have-their-own-store` (where debts live). It names this crash as its fourth hole.
- **Retire.** Pass `encoding="utf-8"` to that `subprocess.run` call. Then `python bin/verdict python lint/rule_audit.py` runs to its end on Windows.
