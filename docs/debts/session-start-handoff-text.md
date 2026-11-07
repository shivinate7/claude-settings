# Session start tells a session to hand off to the batch runner

**What.** `hooks/session_start.sh` line 18 tells a session that wants a merge to hand the branch, head and PR to the batch runner. That contradicts session-tiers (the session tier roles) and waiting-page item 113 a (owner ruling, 2026-11-01 04:26 CST: each PR carries a review record, and there is no merge message). Every session reads this line at start.

**Where.** `hooks/session_start.sh`, line 18, in the session tier text.

- **Decision.** `none`.

**Retire.** Land the line fix after PR #1042 (guard: a coordinator runs no build agents and no merges) merges, because #1042 edits the same line. The line must no longer tell a session to hand a branch, head or PR to the batch runner. Check: a grep of `hooks/session_start.sh` for "hands the branch" finds no match. No test runs this check yet.
