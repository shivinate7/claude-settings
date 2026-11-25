# The compaction-audit remedy is refused by the same rule

**What.** The refusal of rule `compaction-audit` prints a remedy that tells the session to run `precompact_handoff.py --audit-brief`. The same rule refuses that Bash call while the audit is owed. It passes only an `Audit:` spawn and a disk cleanup, and the helper command is neither. So the printed remedy cannot run. After each compaction, in every repo, the session must hand-write the audit brief with the exact transcript path. Fix options: print the transcript path in the refusal, or exempt the helper command's exact form.

**Where.** `hooks/reread_check.py`, `AUDIT_REMEDY` at about :300. `hooks/guard.py`, `COMPACTION_AUDIT_REASON` at :1603 and the `compaction-audit` refusal at :8497. `audit_cleanup_form` at :5656 decides what counts as a disk cleanup. `hooks/precompact_handoff_prompt.md`, step 3 at :29-30.

**Decision.** `precompact-handoff`, its audit rule (item 16) and the `compaction-audit` row of its check table.

**Retire.** The printed remedy runs under the guard. A case in `hooks/test_handoff_wave2.py` runs the printed remedy under the guard with the audit owed, and the call passes.
