# A forbid list with a colon or a slash before its spans is refused

- **What.** A word between the run verb and the colon refuses a spawn's forbid list, such as "Never run these: a stash span, a hard-reset span." A colon right after the run verb passes. A slash between spans refuses too. Either ends the list, so the negator no longer governs the run verb. A list joined by commas or "or" with no word or slash between spans passes. Found in round-3 review, 2026-11-25. Probed on this branch's head. Cost: one refused spawn. Remedy: put the run verb directly before the spans, or drop the backticks.
- **Where.** `hooks/guard.py`, `brief_destructive_hit` and its helper `_brief_prohibits`. On origin/main the scan skips any span that a prohibition clause leads, so these forms pass there. Read in the code; not probed on main.
- **Decision.** `brief-destructive-git` (a spawn brief never orders a working-tree discard).
- **Retire.** `hooks/test_guard.py` runs a case that a builder brief with a colon-led forbid list of spans passes. The case is red on the current code. It goes in the section file tests/guard/s28508-rule9.py.
