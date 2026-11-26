# The compaction-audit remedy is refused by the same rule

**What.** Rule `compaction-audit` refuses every main-session call while the audit is owed, except an `Audit:` spawn and a disk cleanup. Its refusal prints a remedy: run `python3 <absolute path to precompact_handoff.py> --audit-brief --handoff <handoff>`. The guard now lets that exact command through (`audit_remedy_hit`): the printed interpreter, an absolute script path, the printed flags and the session's own handoff, nothing chained. A pass clears nothing; the audit stays owed. What is left: no run of the `compaction-audit` family on the merged code has closed this debt, and no test file runs that family alone. It stays open until the Retire check can run.

**Where.** `hooks/reread_check.py`: `AUDIT_INTERPRETER`, `AUDIT_SCRIPT`, `AUDIT_BRIEF_ARGS` and `audit_remedy_command` (:302-310), the one home of the printed command; `AUDIT_REMEDY` (:313). `hooks/guard.py`: `COMPACTION_AUDIT_REASON` (:1606), `audit_remedy_hit` (:5716) and the `compaction-audit` refusal (:8543-8545). `hooks/precompact_handoff_prompt.md`, step 3 (:29-32).

**Decision.** `precompact-handoff`, its audit rule (item 16) and the `compaction-audit` row of its check table.

**Retire.** The printed remedy runs under the guard. The cases in `tests/guard/s43732-compaction-audit-remedy.py` run the printed remedy under the guard with the audit owed, and the call passes. They run as the `compaction-audit` family of `hooks/test_guard.py` (`GUARD_FAMILY=compaction-audit`); no test file here runs that family on its own, so the close cites a green guard run.
