# The aligned check does not read output-styles Markdown

**What.** Probe group `aligned` reads rule files and the `agents/` and `skills/` Markdown, but not `output-styles/` Markdown, so a sentence there that cites a record can go stale when the record changes and nothing flags it. The owner picked `agents/` and `skills/` only (waiting-page item 872, option b, 2026-11-15 11:33 CST); `output-styles/` is unruled.

**Where.** `lint/compliance_probes.py`, `rule_scope` with `agents_skills`.

**Decision.** `child-cites-not-copies`.

**Retire.** Not yet built. Owner picks whether `output-styles/` Markdown joins the scope. Write the test first, red on the current code: a record changes, an `output-styles/*.md` sentence that cites it stays, the group names that line. `lint/test_compliance_probes.py`
