# The lint reports `e.g.` inside a fence or pre block

- **What.** The lint still reports `e.g.` inside a blockquote fence or a pre block. That is a false alarm.
- **Where.** The lint rules in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Skip fenced and pre text in the lint rule. A test with `e.g.` in each block gives no report.
