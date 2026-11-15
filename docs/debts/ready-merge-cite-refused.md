# A ready merge makes a cite on the old head read red

- **What.** After `merge <pr> --ready` pushes a merge of main, the branch holds H (the old head), then M (a merge of main on H), then P (a page-only commit on M that rebuilds the records page). P is the live head. A `Retire-run:` cite of a green run on H then reads red. `head_under_claims` strips P through `page_only`, but not M, so the cite is checked against M and refused. The harm is a false refusal, not an unsafe act. A debt-closing lane that cites a run by head hits it. How often: unmeasured. Measured by a reviewer probe on a scratch H, M, P repo, round 2 of PR #3440.
- **Where.** `merge/merge.py`, `head_under_claims`, which sets the head a cite is checked against. The refusal text comes from `judge_run` in `lint/check_debt_retire.py`.
- **Decision.** `debt-close-runs-retire` (a `Retire-run:` cite must be a run on the PR head or on a commit above it).
- **Retire.** None yet. Closes when pick b's option a or option c lands (see Ruling). A case in merge/test_merge.py would show it closed. Until then, the remedy is to re-cite after `--ready`, and a close needs a cited run.

## Ruling

- Owner page item 840 a, `own-840-a-ready-merges-main-skip-page-commits`, saved 2026-11-14 19:56:45 CST. It makes `merge <pr> --ready` push a merge of main, and the review record skip page-only commits.
- Coordinator pick b, 2026-11-14 21:00 CST. It accepts this gap and its remedy: re-cite after `--ready`. Undoable. Options not taken, since each widens the merge tool: a, teach the cite read to skip a clean merge; c, no merge at `--ready` for a PR with a cite.
