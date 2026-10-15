# The STE hook timeout can kill the gate

- **What.** The fixer limit (5 s) plus the lint timeout (15 s) equals the hook timeout (20 s). A very large input with many quote marks can reach 20 s. The hook is then killed, and the gate fails open. The old lint timeout failed open the same way.
- **Where.** The timeouts in the STE hook and in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Set the fixer and lint limits below the hook limit, with a margin. A test with a large quote-heavy input finishes inside the hook limit.
