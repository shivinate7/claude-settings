# The bold flag is not enforced

**What.** `bin/merge` prints a line for each changed rule file. The owner sees it only when
the session's report names it in bold, and no check enforces that. A merge made with
`gh pr merge` or the web page prints no flag at all.

**Where.** `merge/merge.py`, the flag lines; `lint/report_gate.py`, which does not read them.

**Decision.** claude-md-change-is-flagged (a CLAUDE.md change is flagged).

**Retire.** The report gate finds each flag line in the turn's merge output and refuses a
report that does not name its path in bold.
