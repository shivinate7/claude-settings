# A local triage session cannot prove its tier

**What.** The guard takes a session's tier only from its cloud tags, read from its own get_session record. A triage session on the owner's Mac or Windows PC has no such record, so the guard refuses each push it makes to the roadmap branch. Harm: local triage cannot keep the roadmap current, and its step notes wait for a cloud triage session.

**Where.** `hooks/guard.py` rule `roadmap-one-writer` (one writer for the roadmap branch). Roadmap step `local-triage-tier-proof` (local triage tier proof).

**Decision.** `session-tiers` (the session shapes).

**Retire.** A local triage session on a Mac and on a Windows PC proves its tier, and its roadmap push passes. A guard test shows the push refused before the fix and passed after it, on both platforms. Any other session's roadmap push stays refused.

## Ruling

Owner, 2026-11-06 15:45 CST (chat, page item 310 a): build the tier file now and merge it fast. This reverses item 213 (2026-11-05 07:44 CST, build nothing yet) within its condition: the fix works on Mac and Windows. Lane `local-triage-tier-build` builds it; decision `session-tiers` holds the design. This debt retires when that lane merges.
