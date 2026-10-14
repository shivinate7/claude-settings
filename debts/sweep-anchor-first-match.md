# The sweep's apply path replaces the first anchor match only

- **What.** `janitor/mutate_sweep.py` checks an anchor exactly once only in its scaffold. Its main apply path still uses a first-match replace, so a second copy inside one file passes silently. All 149 anchors match once today.
- **Where.** The apply path in `janitor/mutate_sweep.py`.
- **Decision.** `guard-split-by-family` (the guard splits into one module per rule family).
- **Retire.** The apply path checks that each anchor matches once, and a case with a second copy goes red.
