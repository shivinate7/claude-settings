# A Markdown rewrite lands when the STE lint cannot run

- **What.** The STE fixer rewrites the text, then the lint cannot run. The rewrite still lands. The log holds `STE-unchecked` and no `fixed` line.
- **Where.** The fixer path of the STE gate, `ste_gate.py`.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** A rewrite that the lint cannot check does not land, or the decision records the accepted risk. A test pins the choice.
