# The compaction-audit remedy was refused by the same rule; the fix lands with this change

**What.** Rule `compaction-audit` refuses every main-session call while the audit is owed, except three: an `Audit:` spawn, a disk cleanup, and the printed remedy. Its refusal prints a remedy: run `python3 <absolute path to precompact_handoff.py> --audit-brief --handoff <handoff>`. The guard now lets that exact command through (`audit_remedy_hit`): the printed interpreter, an absolute script path, the printed flags and the session's own handoff, nothing chained. A pass clears nothing; the audit stays owed. What is left: no run of the `compaction-audit` family on the merged code has closed this debt. It stays open until its Retire check can run. That check passes only on the merged code, and the whole guard suite it runs is longer than the merge tool's limit. The family runs alone as `GUARD_FAMILY=compaction-audit python3 hooks/test_guard.py`.

**Where.** `hooks/reread_check.py`: `AUDIT_INTERPRETER`, `AUDIT_SCRIPT`, `AUDIT_BRIEF_ARGS` and `audit_remedy_command` (:302-310), the one home of the printed command; `AUDIT_REMEDY` (:313). `hooks/guard.py`: `COMPACTION_AUDIT_REASON` (:1606), `audit_remedy_hit` (:5716) and the `compaction-audit` refusal (:8543-8545). `hooks/precompact_handoff_prompt.md`, step 3 (:29-32).

**Decision.** `precompact-handoff`, its audit rule (item 16) and the `compaction-audit` row of its check table.

**Retire.** The printed remedy runs under the guard. The cases in `tests/guard/s43732-compaction-audit-remedy.py` run the printed remedy under the guard with the audit owed, and the call passes. They run as the `compaction-audit` family of `hooks/test_guard.py` (`GUARD_FAMILY=compaction-audit`), so the close cites a green guard run.
