# A merge claim's object window runs past a comma

- **What.** On PR #2058 (branch cannot-claim-follow-up-4; main does not have this code yet), `_non_pr_object` reads the object from a 6-word window that runs past a comma, a parenthesis, "and" or "so". So a merge claim with no PR word passes with no try when a later noun is log(s), doc(s), diff, file(s), config, tag or readme. Main blocks all of these. Harm: the owner is handed a merge the session could do. Found by PR #2058 round 3 review, 2026-11-08 (reviewer sonnet).
- **Where.** `lint/report_guard.py`: `_non_pr_object`, called from `_window_act`.
- **Decision.** `claims-carry-backing` (a definitive prose claim carries its backing or a route row).
- **Retire.** Read the object only up to the first comma or parenthesis. The pinned no-comma lines keep their verdict. A test in `lint/test_report_guard_cannot.py`, red on the current code first, gives each probe and expects a block with no try: "I couldn't merge it, see the logs." / "I can't merge, check the diff." / "I can't merge it (see the logs)." / "I can't merge it and update the docs."
