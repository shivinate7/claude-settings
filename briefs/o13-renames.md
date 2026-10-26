# o13 renames: one word per meaning, in prose and code

Cloud build thread brief, three lanes. Build advisor (4), Oct 26. Base: the main commit that
carries o2 lane 2 (record folders move into docs/); the advisor names it at dispatch. Never rebase
onto main after review. claude-settings only; never push to other repos. Push roadmap edits to the
branch only; only Triage the roadmap (3) republishes.

## Rulings

- shiv, Oct 26: yes to all nine groups of plans/o13-one-word-per-meaning.md (roadmap 12b43eb or
  later). Read that plan first; it is the contract. Read only your groups' sections.
- shiv, Oct 26: the code is renamed too, so his words and the code's words match with no
  conversion table: file names, identifiers, messages, rule anchors, record slugs, rule kinds.
  Only Claude Code's own names stay (deny, block, ask, SubagentStop, subagent_type, the Task tool),
  wrapped in our word (refuse() returns deny).
- A renamed hook file keeps an exit-0 stub at its old path for 14 days (gate-hooks-fail-closed,
  renamed in lane A). Write the removal date in the stub.

## Lanes (one PR each)

- **Lane A, groups 1 and 9 (guard, check; round).** Renames report_gate, ste_gate, feedback_gate,
  test_gates and their records and anchors; rule kind "gate" to "check" in rule_mechanisms.json
  and rule_audit KINDS together; gates.yml and its job to checks; guard.py accepts both
  "Try 3 of 3" and "Round 3 of 3" for 14 days. Branch protection names the required job: do not
  change it yourself; write the exact old and new required-check names in the PR body, so the
  merge step updates protection in the same act. If o15's feedback_gate change has merged, carry
  it; if not, say so in the report.
- **Lane B, groups 2, 3 and 4 (mutation test, red run; command, CI step; agent).** Renames
  harness-scope.sh and test_harness_scope.py, records ask-steps-run-alone, subagent-model-cap,
  subagent-powershell-tool, anchor roles-one-role-per-worker.
- **Lane C, groups 5 to 8 (grant, override; record; finding, defect, safety hole; refuse).**
  Renames anchors outcomes-word-covers-named-act, git-one-entry-per-question,
  verification-never-dry-run-blocklist, records owner-override-pass,
  cite-by-id-blocks-unread-file, reply-judge-samples-never-blocks; guard.py ask texts.

Each lane: every reader of a renamed name changes in the same PR (grep the old name to zero
outside the stub and git history). Edit only the retired sense; a correct sense stays. Add a
GLOSSARY.md row per kept word with a "Not" cell per retired one, in your groups' rows only.
CLAUDE.md lines shared by lanes (the review-cap rule) will conflict at batch time: change only
your words in them; the advisor merges the three.

## Failure classes and proof

- Test-author first, red on base: for each renamed hook or lint file, the old path is a stub that
  exits 0, the new path fires on its case; rule_audit passes with the renamed kinds and anchors;
  a grep test finds no retired name in identifiers, anchors or slugs of your groups.
- Lane A only: a brief with "Try 3 of 3" and one with "Round 3 of 3" both allow the Opus builder;
  a brief with neither still asks (false-alarm and safety-hole cases).
- Run every checks.yml (gates.yml) step locally before sending.
- Lanes A and C change a guard: a fresh Sonnet reviewer reads the diff. Lane B: reviewer too
  (it renames a check's files).

## Report

Cap 20 lines: Done, Deviations, Next. Include "Port to other repos: yes or no, and why" (the
plan says yes, by compliance-check's one-time conversion, a separate step). Send the green,
reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft.
