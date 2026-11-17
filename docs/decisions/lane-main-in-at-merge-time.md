# Main comes into a lane once, at merge time, and only a conflict names a lane

## The ruling

Question: after a merge to main, which lane PRs bring main in, and when?

Rule d: a lane brings main in only on a conflict (skill `ci-hygiene` step 8, the conflict route). A lane that is only behind main is not named. The merge tool does one merge of main into the head at merge time and keeps the green run (decision `merge-needs-current-base`, which holds the clean-merge test and the lint carry).

Based on (ruling): owner, 2026-11-17 14:20 CST, page item 925 `main-in-once-before-lint`, pick d, saved on the page and closed 14:27 CST. His words: "Lanes bring main in only on conflict; the merge tool does one main-in at merge time and keeps the green run (needs #3481 and #3552 on main)."

Based on (ruling): owner, 2026-11-16 13:46 CST, page item 923 pick c, typed in the coordinator's chat, ruling `own-923-c-ready-lanes-bring-main-in`: ready lanes, or lanes one step from ready, bring main in after each merge. Pick d replaces it for ready lanes. It was never filed to a record on main.

- The two changes d needs are drafts, not on main: PR 3481 (the lane lint carries over a clean merge of main) and PR 3552 (the lane lint merges main into a head behind it and pushes the merge on a pass).
- Until both are on main, a lane merges main in by hand at merge time: acts 1 and 4 of step 8, a merge of main and then the lane lint at the new head.
- Open, not built: a grade by priority that would bring some PRs to main together (page item 924). No grade is defined, so nothing here tiers a lane.

Why: pick c would have pushed every ready lane after each merge. Each push is a new head, a new draft run, a new lint and a new record, and the lint runs one PR at a time (runner report, 2026-11-16 13:46 CST, unmeasured). Pick d pays one main-in per lane, at the merge, when the lane is about to land.

Outcome protected: the ready queue stays clean, and a ready lane keeps its green run until it merges.

Kind: process
Home: skills/ci-hygiene/SKILL.md

Cost: per merged lane, one merge of main into its head, one push, and one lane lint at the new head (unmeasured). Until PR 3481 and PR 3552 land, the lane does these by hand and its run starts again (unmeasured).

Risk: unlikely. A clean merge can still break a suite, and main's run after the merge finds it (decision `merge-needs-current-base`).
