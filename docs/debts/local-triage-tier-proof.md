# A local triage session cannot prove its tier

**What.** The guard takes a session's tier only from its cloud tags, read from its own get_session record. A triage session on the owner's Mac or Windows PC has no such record, so the guard refuses each push it makes to the roadmap branch. Harm: local triage cannot keep the roadmap current, and its step notes wait for a cloud triage session.

**Also.** A local lane session has no cloud id either. `override.remote_session_id` reads the id only from `CLAUDE_CODE_REMOTE_SESSION_ID`. So rule `orchestrator-merge-write` (decision `builders-cannot-edit-tests`, the merge route) allows a local lane's merge write, and logs `orchestrator-merge-write-unread` (test hooks/test_guard.py::orchestrator-merge-write: an Edit in a merge with no session id in the env is allowed and logged orchestrator-merge-write-unread). Harm: a local lane can resolve a merge's test or product conflict itself, the act this rule exists to stop. The owner ruling below applies: build nothing on local identity until a Mac and Windows fix exists.

**Where.** `hooks/guard.py` rule `roadmap-one-writer` (one writer for the roadmap branch). Roadmap step `local-triage-tier-proof` (local triage tier proof). For the local lane: `override.remote_session_id` in `hooks/override.py`, read by `orchestrator_merge_write_hit` in `hooks/guard.py`.

**Decision.** `session-tiers` (the session shapes). For the local lane: `builders-cannot-edit-tests` (the merge route).

**Retire.** A local triage session on a Mac and on a Windows PC proves its tier, and its roadmap push passes. A guard test shows the push refused before the fix and passed after it, on both platforms. Any other session's roadmap push stays refused. A local lane session's merge write of a conflicted product file is refused on both platforms.

## Ruling

Owner, 2026-11-05 07:44 CST (Cockpit item `local-triage-tier-word`, local triage tier word): no tier word, and not cloud-only. A tier-file fix is acceptable only when it works on both Mac and Windows. Until such a fix exists, build nothing; this debt holds the gap.
