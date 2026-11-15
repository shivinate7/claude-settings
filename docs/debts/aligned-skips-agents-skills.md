# The aligned check reads rule files only, not agents/ or skills/

**What.** Round 1 review found `agents/reviewer.md` lines 75-77 copy text of `hold-unsafe-after-round-3` and cite it. Probe group `aligned` reads `CLAUDE.md`, `.claude/rules`, `docs/rules` and the root rule files, so a record change leaves that copy stale and nothing flags it. 29 records are cited only from `agents/`, `skills/`, `hooks/`, `lint/` or `output-styles/` Markdown. Measure: round 1 reviewer's census on `17336c1e`; not re-run.

**Where.** `lint/compliance_probes.py`, probe groups `aligned` and `restates`: the rule-file scope (`rule_scope`).

**Decision.** `child-cites-not-copies`.

**Retire.** Not yet built. Owner picks whether `agents/`, `skills/` and `output-styles/` Markdown join the scope. Write the test first, red on the current code: a record changes, an `agents/*.md` sentence that cites it stays, the group names that line.
