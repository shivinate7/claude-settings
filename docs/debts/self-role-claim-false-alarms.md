# The self-role-claim guard refuses a no-effect assignment and quoted claim text

**What.** Guard rule `self-role-claim` refuses two forms that claim nothing. A bare `CS_SESSION_ROLE=triage` line is refused, though it sets a shell variable no child inherits. Quoted text at command position is refused, such as a quoted list line `"export CS_SESSION_ROLE=triage"`, because the tokenizer drops quotes and the line reads as an `export`. Harm: a session that writes such a line is refused on text that claims no role.

**Where.** `hooks/guard_merge.py`, `_claims_a_role`, reached through `self_role_hit`. Its prefix check reads `CS_SESSION_ROLE=` before the command word, and the tokenizer hands it the quote-free text.

**Decision.** `session-tiers` (session roles), its `self-role-claim` bullet.

**State.** The read forms are fixed: `claude-role --help` and `-h` (judged per segment), `command -v` and `-V` on the launcher, and `$role = $env:CS_SESSION_ROLE` pass. The cases in `tests/guard/s13410-local-role.py` (sections "SELF-ROLE-CLAIM, READS", "CLAIMS" and "THE CLAIM'S REASON") pin them.

**Retire.** Read the quote state of the command word, so a quoted line is text, and let a bare `CS_SESSION_ROLE=x` with no command word after it pass. Add a green control for each in `tests/guard/s13410-local-role.py`, and keep every claim form there denied (`export CS_SESSION_ROLE=triage`, `(claude-role triage)`, `Set-Item` on `Env:`, the spaced `SetEnvironmentVariable` call, `claude-role triage --help`).
