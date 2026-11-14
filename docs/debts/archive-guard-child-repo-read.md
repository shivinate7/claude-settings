# The archive guard cannot read a child lane's repo until add_repo attaches it

- **What.** The archive guard cannot read a child lane's repo until `add_repo` attaches that repo to the session. On 2026-11-13 it refused three times on lane `session-mailbox-followups`. The fix was `add_repo` at 09:08 CST. When gh answers 403 or 404 for the repo, the refusal names `add_repo <owner>/<repo> (read)` for that repo only. The session must still attach the repo by hand before the guard can read it.
- **Where.** `hooks/guard_merge.py`, `archive_hit` and `_stranded_branch`.
- **Decision.** `session-tiers`, a lane closes only after its records pull request has landed.
- **Retire.** The guard attaches or reads a lane's child repos by itself, so an unattached second repo no longer refuses the archive. Add a case to `hooks/test_guard.py` where the lane's second repo answers 403 and the archive is allowed, then `env GUARD_FAMILY=lane-closes-after-records python3 hooks/test_guard.py` passes with it. The refusal wording alone does not close this debt: the current 403 cases pin the refusal, and they are not that case.
