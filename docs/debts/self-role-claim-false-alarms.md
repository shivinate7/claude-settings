# The self-role-claim guard refuses two reads as claims

**What.** Guard rule `self-role-claim` refuses two reads as role claims. `$role = $env:CS_SESSION_ROLE` is refused, because a segment that names `$env:CS_SESSION_ROLE` with any token starting with `=` counts as a claim. `command -v claude-role` is refused as a launcher run. Harm: a session that debugs the launcher is refused on a read, though the rule's own doc says reads pass.

**Where.** `hooks/guard_merge.py`, `_claims_a_role`, reached through `self_role_hit`. Its two conditions are the `$env:` variable token with any `=`-leading token, and the launcher as the command word.

**Decision.** `session-tiers` (session roles), its `self-role-claim` bullet.

**State.** Found in review round 3 of lane local-tier-file.

**Retire.** Take `=` only as the token right after the variable, and skip `command -v` in the launcher check. The runnable test `tests/guard/test_self_role_claim.py` (not yet written) holds a green control for each read form (`which`, `type`, `ls`, `Test-Path` on `Env:`, `$role = $env:CS_SESSION_ROLE`, `command -v claude-role`) and keeps each claim form denied (`export CS_SESSION_ROLE=triage`, `(claude-role triage)`, `Set-Item` on `Env:`, and the spaced `SetEnvironmentVariable` call).
