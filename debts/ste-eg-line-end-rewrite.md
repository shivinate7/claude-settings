# An `e.g.` at a line end becomes a full stop

- **What.** `e.g.` or `i.e.` at a line end becomes `for example.` or `that is.` with a full stop. That breaks hard-wrapped prose. Example: a sentence that wraps after `e.g.` ends early.
- **Where.** The autofix rules in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Skip the rewrite at a line end. A test with a wrapped `e.g.` keeps the line break and the sentence intact.
