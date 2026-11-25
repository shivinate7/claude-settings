# A forbid list with a colon or a slash before its spans is refused

- **What.** The brief scan refuses a spawn whose forbid list puts a colon before its spans, such as "Never run these: a stash span, a hard-reset span." A colon before the spans refuses the list even when the spans join with "or". A slash between spans refuses it too. A colon or a slash ends the list, so the forbidding word no longer governs the run verb. A list joined by commas or "or" with no colon passes. Found in round-3 review, 2026-11-25. Probed on this branch's head. Cost: one refused spawn. Remedy: join the spans with "or", or drop the backticks.
- **Where.** `hooks/guard.py`, `brief_destructive_hit` and its helper `_brief_prohibits`. On origin/main the scan skips any span that a prohibition clause leads, so these forms pass there. Read in the code; not probed on main.
- **Decision.** `brief-destructive-git` (a spawn brief never orders a working-tree discard).
- **Retire.** `hooks/test_guard.py` runs a case that a builder brief with a colon-led forbid list of spans passes. The case is red on the current code. It goes in the section file tests/guard/s28508-rule9.py.
