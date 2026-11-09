# A push never sends a merge of more than two parents

## The ruling

Rule `octopus-push` in `hooks/guard.py` refuses a `git push` whose new commits hold a merge with more than two parents. Its home is `octopus_push_hit` in `hooks/guard_merge.py`, beside `conflict_markers_hit`, which shares its push reader (`_push_refs`). Layer: the coordinator, 2026-11-08 20:04 CST, option a for the fork-flow limit below.

- The mistake: a lane joins two old heads with one `git commit-tree` that has three parents, and pushes it (incident, lane record-after-each-round, PR #1908, commit 333c91a6f, 2026-11-08 18:46 CST).
- The harm: `lint/check_silent_undo.py` reads only two-parent merges and answers UNKNOWN for a merge with more, so the lane lint can never pass. The merge stays in the lane's range, so only a history rewrite or a new PR clears it.
- A hit: a commit with three or more parents in `<source> --not --remotes=<remote>`, one `git rev-list --merges --parents` per pushed ref. The remote is the one the push names, else `origin`. A merge that a ref of the pushed remote already holds is not new, so a lane that merges in an old octopus passes.
- The remedy names the two-parent form: redo that merge as a chain of two-parent merges, then push.
- Out of scope: a push to `main` or `master` keeps the `push-main` ask and reads nothing. A dry run (`--dry-run`, `-n`) sends nothing and passes.
- Known limit, the fork flow: an octopus held only by another remote's refs, such as `upstream/main` merged into a lane pushed to a remote that lacks it, is refused. The remedy cannot fix someone else's commit. This is the safe side, the flow is rare here, and the owner's typed `override` lifts it (`owner-override`). Kept by the coordinator, 2026-11-08 20:04 CST, over reading every remote.
- A remote given as a URL or path that no `remote.<name>.url` names reads every remote's refs, so it is not refused for an old octopus.
- Not read, kept as notes in `docs/debts/notes.md` (`guard-guards-mistakes-only`). A merge and a push in one command. A shell-variable source, read as HEAD. A bare push on a branch that pushes to a remote other than origin. `bash -c` and `eval`. `--all`, `--mirror` and a tags-only push.
- Why not read it in `check_silent_undo`: that lint answers UNKNOWN for a merge of more than two parents, and reading one as pairwise merges is the other fix shape in step octopus-merge-push-refused. The guard stops the merge before it reaches a branch, so the lint never has to judge one.
- Cost: per pushed ref, one `git rev-list`, and none for a dry run or a `main` or `master` destination. A URL or path remote adds one `git config` read per pushed ref. `record_push_cost_case` in `hooks/test_guard.py` pins the counts for plain-name remotes. The URL and path read is not pinned. No log, file or process.

Protected by the `octopus-push` cases in `hooks/test_guard.py`, red before the rule landed, and by the remedy-text check, which went red on two mutants. The `main` skip has a case for `main` only, none for `master`.

Kind: process
Home: hooks/guard.py
