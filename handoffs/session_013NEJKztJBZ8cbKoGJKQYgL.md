# lane: batch68-mockup-home-wrong-cause (session_013NEJKztJBZ8cbKoGJKQYgL), received 09:50 CST 2026-11-10, kind B

Handoff (B), lane batch68-mockup-home-wrong-cause. No commits, nothing to push; I built nothing.
1. Worked on: diagnosis only of the red checks-mutate-guard mutant (mockup-home refuse arm), batch-68h d39081041, PR #2441.
2. Cause, already sent to session_013NEJL2hB1pLZPDpzas7VgB: hooks/question_form.py:1462 (cross_repo_hit) imports stale_pages from ../skills/waiting-page; the mutant tree (mutate_shared.guard_tree + mutate_guard.run_mutant) has no skills/, so stage 1 crashes and falls back to the full suite. Lane: commit 8806fdcf5 (likely PR #2229).
3. Fix, not built: in run_mutant's guard/simlease arm, copytree skills/waiting-page into root/skills/waiting-page beside the lint copy.
4. Left: someone builds that fix on the lane branch, then re-runs checks-mutate-guard; the full tool path was not run to the end by me in a clean tree.
