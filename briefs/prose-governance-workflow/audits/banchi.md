**Done**
- OTHER: Audit of /home/user/shivinate7/banchi/CLAUDE.md. It is 411 lines, and AGENTS.md is a symlink to it. There is no .claude/CLAUDE.md, and .claude/rules holds only a README. Cut target: about 100 lines if the docs-audit rows below are re-pointed in the same lane. If no row changes, about 250 (estimate, unmeasured).
- Lines per class (50 more lines are headings, blanks and fences): KEEP 78, PATH 107, DUP 51, MOVE 121, STALE 4.
- Five biggest cuts:
  1. Commands, lines 30-136: 84 lines are MOVE or STALE. `make help` (scripts/make-help.py reads Makefile comments) and `./banchi -h` already print them. Keep about 16. Lines 52 and 60 document retired stub targets (Makefile:853 and :1340). Blocker: the `commands roster` row (scripts/docs_audit/paths_commands.py, check_commands_roster) counts a target as documented only if it has a CLAUDE.md bullet, is in the `make check` recipe, or is on the shrink-only commands-internal.json list. Fix: count a Makefile comment as documented.
  2. The front end, lines 137-217: 64 lines are PATH (`app/**`). The route list at lines 154-160 is MOVE, because ROUTES and the README route table hold it.
  3. Things you will get wrong, lines 231-290: 50 of 57 lines go. 34 are PATH (pipeline/, store/, server/, cli/). 15 are MOVE: the storage-key roster (lines 253-263) and the server constants (lines 233-239) live in code. Removing line 247 fails the `paid-read model` row (status_reach.py, model_disagreement). Removing lines 233-239 fails the `server concurrency` row (code_invariants.py). Whether the `storage keys` row fails is unknown.
  4. Hard rules, lines 291-360: 31 DUP and 10 MOVE.
     - Main moves by PR (343-359) restates git-main-only-by-pr (main moves only by pull request) and git-integration-branch-merge (batch lanes into one integration PR).
     - The settled-decision rule restates outcomes-decision-is-argument and outcomes-stale-decision-protocol.
     - Fix the cause restates building-fix-cause-not-symptom. One home restates building-one-home-per-capability. No dates restates speak-rewrite-superseded-in-place.
     - The shell-guard hatch detail (330-336) is MOVE to D179 (shell mistakes are refused).
     - Blocker: the `rule enforcement` row pins HARD_RULE_FLOOR=13 against 15 bullets today, and requires PROSE_ONLY_EXPECTED to be exactly 6 (scripts/docs_audit/rules.py:67-68). Each NOT MECHANIZED cut moves that pin.
  5. Working agreement, lines 361-382: 13 DUP. The report format restates reports-order-of-labels, reports-done-format and reports-blockquote-no-fence. The model lines restate roles-sonnet-is-the-ceiling and roles-third-round-steps-up. The design pass restates roles-one-role-per-agent. Land design restates building-land-design-or-abandon. Compacting restates tokens-compacting-keep-essentials.
- KEEP rules that are wrong or unclear:
  - Lines 347-349 are STALE. They say the coordinator "merges on green checks" and a lane "never merges". /home/user/claude-settings/docs/decisions/standing-merge-grant.md says "The coordinator never merges" (owner, 2026-11-01 21:34 CST), and that a one-lane session the owner started merges its own lone lane (owner, 2026-11-02 15:14 CST). This is a duplicated parent rule that went out of date.
  - Lines 332-333 and 358 list the owner-held hatches (BANCHI_CHECKOUT through BANCHI_MAIN) as "never printed to an agent", yet they sit in the file every agent loads.
  - Some decision glosses stop mid-phrase: D313 at line 186 reads "(Nothing on screen moves unless the)", and D325 at line 79 and D316 at line 139 are cut short too. Line 332 writes D042 where the rest of the file writes D42.
  - Line 322 ("Grep ... the Commands block") and line 381 ("keep ... every `make` command") stop working once Commands is cut. Re-point them to `make help`.
- Mechanical check: one exists but did not stop this. check_claude_md_size.py only warns (exit 0) and runs only in claude-settings CI and compliance-check, never in banchi's CI or hooks. Banchi's own rows also pull text into the file: the commands roster, the rule-count pins and the claim rows.

**Deviations**
- Running `./banchi --help` wrote /home/user/shivinate7/banchi/__pycache__/. It is gitignored, git status is clean, and I left it in place.

**Input Needed**
- D135 (Codex reads the same rules): .codex/ holds only hooks.json and .agents/ only skills, so nothing mirrors .claude/rules. Every PATH move would drop that rule for Codex unless nested AGENTS.md files are added. Lane banchi-claude-md-cut (on banchi PR #1036) should decide how to handle this.

**Next**
- Compare this audit with PR #1036's cut. I did not read that PR.