# A local triage session cannot prove its tier

**What.** The guard takes a session's tier only from its cloud tags, read from its own get_session record. A triage session on the owner's Mac or Windows PC has no such record, so the guard refuses each push it makes to the roadmap branch. Harm: local triage cannot keep the roadmap current, and its step notes wait for a cloud triage session.

**Where.** `hooks/guard.py` rule `roadmap-one-writer` (one writer for the roadmap branch). Roadmap step `local-triage-tier-proof` (local triage tier proof).

**Decision.** `session-tiers` (session roles).

**State.** The code is built (lane local-tier-file): the launcher writes a role file, and the guard reads it for the roadmap push and for a local confirm. A local confirm is judged by the session's own file only. (a) An own file must name batch-runner, and the guard also checks the repo. (b) With no own file and no CS_SESSION_ROLE, today's behaviour stands. (c) CS_SESSION_ROLE set with no matching own file refuses (decision `session-tiers`, Local sessions). The debt stays open until the measurement below.

**Retire.** A local triage session on a Mac and on a Windows PC proves its tier, and its roadmap push passes. A guard test shows the push refused before the fix and passed after it, on both platforms. Any other session's roadmap push stays refused. The retire check is a real push: a triage session started with `claude-role triage` pushes to the roadmap branch on a Mac and on a Windows PC. It passes there, which also measures that the hook's session id equals the Bash call's `CLAUDE_CODE_SESSION_ID` on Windows.

## Ruling

Owner, 2026-11-05 07:44 CST (Cockpit item local-triage-tier-word, local triage tier word): no tier word, and not cloud-only. A tier-file fix is acceptable only when it works on both Mac and Windows. Owner pick b (item local-triage-tier-word, choice b): a tier file that only the computer's setup writes, which Claude cannot write. Built in lane local-tier-file.
