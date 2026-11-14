# The gate needs the handoff path in exact form

**What.** The gate counts a spawn only when its brief holds the session's exact absolute handoff path. The prompt's step 2 shows the path with a tilde, `~/.claude/handoffs/<session_id>.md`. A brief written with the tilde, or with a Windows slash form, does not match. The refusal names the handoff path but never says why the spawn did not count.

**Where.** `hooks/precompact_handoff.py`: the path test in `_gate_scan`, and the refusal text in `_gate_reason`.

**Decision.** `precompact-handoff`, checkpoints keep the handoff current (item 4, the Sonnet subagent gate).

**Retire.** The tilde form counts, and a refusal for a brief with the wrong path names the exact path and says the brief did not name it. `hooks/test_precompact_handoff.py` holds a case for each. Both cases go red on the current code.
