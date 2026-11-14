# The merge remedy sends a cloud lane into the merge role refusal

**What.** The remedy text for `merge <pr> --confirm` sends a cloud lane into the merge role refusal (read hooks/guard_merge.py:214-219) (read merge/merge.py:4531-4532) (test merge/test_merge.py::test_no_role_file_refuses_before_any_host_read_or_lock). Both remedies also omit `--head` (read hooks/guard_merge.py:214-219) (read hooks/guard_merge.py:266-271). A batch runner is refused without `--head` (read merge/merge.py:4533-4534). A cloud session's merge role is read by `read_merge_role` (read merge/merge.py:4261-4274).

**Where.** `hooks/guard_merge.py`, the remedies in `MERGE_CHECK_REASON` and `BARE_MERGE_REASON` (read hooks/guard_merge.py:214-219) (read hooks/guard_merge.py:266-271). It breaks rule `git-remedy-never-names-target`, which says a refusal's printed remedy never names the forbidden target (read CLAUDE.md:54-55).

**Decision.** `session-tiers`, session roles (read docs/decisions/session-tiers.md). `auto-mode-owner-acts`, which acts auto mode allows with no ask (read docs/decisions/auto-mode-owner-acts.md).

**Retire.** Add a case to `hooks/test_guard.py` (read hooks/test_guard.py). A cloud lane's merge remedy must not send it into the merge role refusal. Each merge remedy must name `--head`. The case is red on the current remedies and green once they are fixed.
