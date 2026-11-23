# A ready merge makes a relayed yes read as moved

- **What.** After `merge <pr> --ready` pushes a merge of main, the live head is P (a page-only commit) on top of M (the merge of main) on top of H (the old head). A relayed yes that names H is then refused with `HEAD_MOVED`. `relayed_head_holds` accepts, between the named head and the live head, only Record-claim commits, their reverts, page-only commits, same-tree commits, and, where `merge.requiredChecks` is "none" and the base is the default branch, a clean merge of main. M is a merge of main, so it passes only under that setting and only when its tree is git's own clean merge. The harm is a false refusal, not an unsafe act: the owner must send the yes again. A lane that relays a yes before `--ready` hits it. How often: unmeasured. Measured by a reviewer probe on a scratch H, M, P repo, round 2 of PR #3440.
- **Where.** `merge/merge.py`, `relayed_head_holds`. It runs at the merge step and at `merge <pr> --confirm --head`, and either refusal raises `HEAD_MOVED`.
- **Decision.** `auto-mode-owner-acts` (a relayed yes binds to the head at relay time).
- **Retire.** None yet. Closes when pick b's option a or option c lands for this read (see Ruling). A case in merge/test_merge.py would show it closed. Until then, the remedy is to send the yes again after `--ready`, and a close needs a cited run.

## Ruling

- Owner page item 840 a, `own-840-a-ready-merges-main-skip-page-commits`, saved 2026-11-14 19:56:45 CST. It makes `merge <pr> --ready` push a merge of main, and the review record skip page-only commits.
- Coordinator pick b, 2026-11-14 21:00 CST. It accepts this gap and its remedy: send the yes again after `--ready`. Undoable. Options not taken: a, teach the relayed-yes read to skip a clean merge; c, no merge at `--ready` for a PR with a relayed yes. Each is a tool-wide change, not widening. Widening means one repo's differing form made to pass (item 734 (widening means one repo), owner 14:19 CST Nov 17).
