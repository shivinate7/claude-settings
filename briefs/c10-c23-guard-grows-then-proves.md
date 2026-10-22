Guard rule amendment and fire counts, claude-settings. Roadmap: c10 (the guard rule, amended) and l1 (track guard refusals per session). This prepares c23 (cull the guard itself), which is not part of this brief. Make it its own small batch after the one running now (the hook import, process-start and Windows lanes), because it touches CLAUDE.md and lint/, and those lanes are already editing files near them. No measuring step; prove each change with a test.

Owner's ruling, Oct 21: let the guard grow while things change, then cull what never proved itself. No freeze was ever in force. The current rule stays and gets wider.

Lane 1, amend building-guard-needs-incident in place. CLAUDE.md, around line 82: "Build a new guard or gate rule only against a named incident or a measured risk. Cite it in the rule's record." Rewrite it in place, as one rule with no new section, to say:
- A new guard or gate rule may land for a named incident, a measured risk, or a likely risk (likely to hit in normal work, the same bar debts use).
- Its record says which of the three it is, and the date the rule landed.
- At each cull, a guard rule that never fired in guard.log since it landed, and whose record names no incident, is deleted with its code and tests.
Update the rule's row in docs/records.md (line 77) and in lint/rule_mechanisms.json, whose reason text names only "a named incident or measured risk". Record the ruling in place under decisions/ if a decision holds this rule; otherwise in the rule's record. One-line reason: "grow while things change, then cull what never fired (owner, Oct 21)". Report the rule text before and after, and the word change.

Lane 2, rules that never fired show up. lint/guard_log_report.py already prints deny, ask and noted counts per rule from guard.log, and guard.log is never pruned. The gap: a rule that never fired has no line, so it never appears, and those are exactly the rules a cull is looking for. Add a flag (for example --all-rules) that lists every rule id the guard and the gates can emit, each with its counts, including 0, plus the date of the rule's first guard.log line (or "never"). Take the rule ids from their one home in the code, not a copied list (rule building-allow-list-is-the-constant). Let --days take "all" for the whole log. Tests: a rule with no lines shows 0 and "never"; a rule with lines shows its counts and first date; the list matches the constant, red on main and green on the fix.

Do not delete any guard rule in this batch. That is c23, the guard cull, after this lands.

Report: per lane, what changed and the test that proves it; the rule text before and after; and one run of the new report on this machine with --all-rules --days all, pasted in full, so the cull can start from it.
