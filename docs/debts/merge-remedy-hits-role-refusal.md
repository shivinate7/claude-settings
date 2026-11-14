# The merge remedy sends a cloud lane into the merge role refusal

**What.** The remedy text for `merge <pr> --confirm` now sends a cloud lane into the merge role refusal. Both remedies also omit `--head` (read hooks/guard_merge.py MERGE_CHECK_REASON, BARE_MERGE_REASON). A batch runner is now refused without `--head` (read merge/merge.py BATCH_RUNNER_NEEDS_HEAD). A cloud session's merge role is read by `read_merge_role` (read merge/merge.py read_merge_role).

**Where.** `hooks/guard_merge.py`, the remedies in `MERGE_CHECK_REASON` and `BARE_MERGE_REASON` (read hooks/guard_merge.py MERGE_CHECK_REASON). It breaks rule `git-remedy-never-names-target`, which says a refusal's printed remedy never names the forbidden target (read CLAUDE.md).

**Decision.** `session-tiers`, session roles (read docs/decisions/session-tiers.md). `auto-mode-owner-acts`, which acts auto mode allows with no ask (read docs/decisions/auto-mode-owner-acts.md).

**Retire.** Add a case to `hooks/test_guard.py` (read hooks/test_guard.py). A cloud lane's merge remedy must not send it into the merge role refusal. Each merge remedy must name `--head`. The case is red on the current remedies and green once they are fixed.
