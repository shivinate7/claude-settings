# A ready merge makes a relayed yes read as moved

- **What.** After `merge <pr> --ready` pushes a merge of main, the live head is P (a page-only commit) on top of M (the merge of main) on top of H (the old head). A relayed yes that names H was refused with `HEAD_MOVED`, because `relayed_head_holds` then accepted only Record-claim commits, their reverts and page-only commits between the named head and the live head. PR 3820 (proof carries over heal) also accepts clean merges of the default base there, so M no longer refuses. No case or cited run shows it yet. The harm was a false refusal, not an unsafe act: the owner had to send the yes again. A lane that relays a yes before `--ready` hits it. How often: unmeasured. Measured by a reviewer probe on a scratch H, M, P repo, round 2 of PR #3440.
- **Where.** `merge/merge.py`, `relayed_head_holds`. It runs at the merge step and at `merge <pr> --confirm --head`, and either refusal raises `HEAD_MOVED`.
- **Decision.** `auto-mode-owner-acts` (a relayed yes binds to the head at relay time).
- **Retire.** Not closed. A case in merge/test_merge.py that shows a relayed yes accepted across M closes it, with a cited run. Until a case exists, the remedy stands: send the yes again after `--ready` if the read refuses.

## Ruling

- Owner page item 840 a, `own-840-a-ready-merges-main-skip-page-commits`, saved 2026-11-14 19:56:45 CST. It makes `merge <pr> --ready` push a merge of main, and the review record skip page-only commits.
- Coordinator pick b, 2026-11-14 21:00 CST. It accepts this gap and its remedy: send the yes again after `--ready`. Undoable. Option a, teach the relayed-yes read to skip a clean merge, is in PR 3820 for the default base. Option c, no merge at `--ready` for a PR with a relayed yes, is not taken. Each is a tool-wide change, not widening. Widening means one repo's differing form made to pass (item 734 (widening means one repo), owner 14:19 CST Nov 17).
