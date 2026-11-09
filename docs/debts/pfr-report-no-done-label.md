# A reviewer report with no Done label is not read

- **What.** A reviewer report whose first line is the bare verdict (no Done label) is not read. Neither is a verdict line with trailing text, or a drifted form: a bold word, an em dash, or a `Verdict:` prefix. In one real lane transcript, 7 of 15 distinct reviewer reports gave no verdict, including the round 1 FAILs of PR 1628 and PR 1801. A push after them is allowed: incident class PR 1467 (push before the FAIL record).
- **Where.** The report reader in `hooks/guard_push_delete.py` (`_DONE_LABEL`, `_VERDICT_LINE`).
- **Decision.** `push-needs-review-record` (a push needs the review record of its FAIL).
- **Retire.** Read the first non-blank report line as the Done line, and match the verdict line as a prefix. A case with each drifted form refuses the push, shown by `hooks/test_guard.py`.
