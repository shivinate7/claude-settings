# The merge remedy sends a cloud lane into the merge role refusal

**What.** The remedy text for `merge <pr> --confirm` now sends a cloud lane into the merge role refusal. Both remedies also omit `--head`. A batch runner is now refused without `--head`.

**Where.** `hooks/guard_merge.py`, the two remedies at lines 210-214 and 272-276. It breaks rule `git-remedy-never-names-target`, which says a refusal's printed remedy never names the forbidden target.

**Decision.** `session-tiers`, session roles. `auto-mode-owner-acts`, which acts auto mode allows with no ask.

**Retire.** Add a case to `hooks/test_guard.py`. A cloud lane's merge remedy must not send it into the merge role refusal. Each merge remedy must name `--head`. The case is red on the current remedies and green once they are fixed.
