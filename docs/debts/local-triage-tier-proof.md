# A local triage session cannot prove its tier

**What.** The guard takes a session's tier only from its cloud tags, read from its own get_session record. A triage session on the owner's Mac or Windows PC has no such record, so the guard refuses each push it makes to the roadmap branch. Harm: local triage cannot keep the roadmap current, and its step notes wait for a cloud triage session.

**Where.** `hooks/guard.py` rule `roadmap-one-writer` (one writer for the roadmap branch). Roadmap step `local-triage-tier-proof` (local triage tier proof).

**Decision.** `session-tiers` (the session shapes).

**Retire.** A local triage session on a Mac and on a Windows PC proves its tier, and its roadmap push passes. A guard test shows the push refused before the fix and passed after it, on both platforms. Any other session's roadmap push stays refused.

## Ruling

Owner, 2026-11-05 07:44 CST (Cockpit item `local-triage-tier-word`, local triage tier word): no tier word, and not cloud-only. A tier-file fix is acceptable only when it works on both Mac and Windows. Until such a fix exists, build nothing; this debt holds the gap.
