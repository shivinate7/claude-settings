# The self-role-claim guard refuses a lookup, a no-effect assignment and quoted claim text

**What.** Guard rule `self-role-claim` refuses three forms that claim nothing. `command -v claude-role` and `command -V claude-role` are refused: they print a path and start no session. A bare `CS_SESSION_ROLE=triage` line is refused, though it sets a shell variable no child inherits. Quoted text at command position is refused, such as a quoted list line `"export CS_SESSION_ROLE=triage"`, because the tokenizer drops quotes and the line reads as an `export`. Harm: a session that writes one of these is refused on text that claims no role.

**Where.** `hooks/guard_merge.py`, `_claims_a_role`, reached through `self_role_hit`. Its prefix check reads `CS_SESSION_ROLE=` before the command word, the tokenizer hands it the quote-free text, and the launcher as command word passes only with help flags.

**Decision.** `session-tiers` (session roles), its `self-role-claim` bullet.

**State.** The help reads are fixed: `claude-role --help` and `-h` (judged per segment) and `$role = $env:CS_SESSION_ROLE` pass. The `command -v` pass was tried and removed: a segment cannot see that a lookup's output runs in a later one (`$(command -v claude-role) triage`, `path=$(command -v claude-role); "$path" triage`), so the lookup stays refused. The cases in `tests/guard/s13410-local-role.py` (sections "SELF-ROLE-CLAIM, READS", "CLAIMS" and "THE CLAIM'S REASON") pin each.

**Retire.** Read the quote state of the command word, so a quoted line is text, and let a bare `CS_SESSION_ROLE=x` with no command word after it pass. Let `command -v` pass only when the call reads the whole command line and sees that no later segment runs its output. Add a green control for each in `tests/guard/s13410-local-role.py`, and keep every claim form there denied (`export CS_SESSION_ROLE=triage`, `(claude-role triage)`, `Set-Item` on `Env:`, the spaced `SetEnvironmentVariable` call, `claude-role triage --help`, `$(command -v claude-role) triage`).
