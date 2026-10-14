# PR2 needs a case that kills a sibling mutant

- **What.** PR2 needs a case that kills a sibling mutant through the in-process load in `hooks/test_guard.py`. That load puts the real `hooks/` first on `sys.path`.
- **Where.** The in-process load in `hooks/test_guard.py`.
- **Decision.** `guard-split-by-family` (the guard splits into one module per rule family).
- **Retire.** The case is added in PR2, and it goes red on the sibling mutant before the fix.
