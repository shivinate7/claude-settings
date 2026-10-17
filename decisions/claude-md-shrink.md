# CLAUDE.md drops the prose of a rule that a guard or gate enforces

## The question

How short can the root `CLAUDE.md` get, when a guard or gate already enforces a rule?

## Ruling

Owner ruling, 2026-10-16 23:53 CDT. In short:

- Delete the prose of each guard or gate rule.
- Keep a reminder of 3 words or fewer where agents hit the guard often.
- Re-kind an `unmechanized` rule to `judgment` when its reason already says no check can judge it.
- Never reword a kept rule.

Owner ruling, 2026-10-17 00:40 CDT:

- `judgment` means that no exact check can judge the rule. A model hook that comments on a reply is not an exact check.
- A reason that says no check reads the rule yet stays `unmechanized`. Only a reason that says no check can judge it moves to `judgment`.

Owner, 2026-10-17 02:28 CDT: "Merge it." The second lane scored zero net value at review round 3. Its one opened hole (hole 14) comes from the deleted rules themselves.

Owner interview, 2026-10-17 (00:44 to 01:55 CDT), on the 23 rules left by the first lane:

- `roles-sonnet-is-the-default`: delete only the sentence "An unlisted agent runs Sonnet, and that needs no word." Re-kind the row to `unmechanized`.
- `roles-workers-never-spawn`: delete prose, anchor and row. Debt `nesting-risk-unrecorded`.
- `shared-trees-no-machine-wide-kill`: keep only the two sentences on killing and restarting. Keep anchor and row.
- `git-wait-for-required-checks`: delete prose, anchor and row.
- `git-draft-until-reviewed`: delete prose, anchor and row.
- `verification-recovery-not-gated-on-own-state`: keep the text. Re-kind the row to `unmechanized`.
- `speak-cite-id-plus-gloss`: keep. Debt `slug-cite-gloss-unchecked`.
- `reports-no-report-when-nothing-landed`: keep the text. Re-kind the row to `unmechanized`. Debt `report-on-empty-turn-unchecked`.
- `output-write-in-ste`: goes to a separate lane.
- The other 14 rules of the 23 stay as they are.

Precedent: `a-rule-with-no-gate-leaves-claude-md` (a rule the owner took off the gate leaves `CLAUDE.md` too).

## What landed, MEASURED on branch `claude-md-shrink` (a1655ad) against main

- Six rules lose their prose, anchor and row in `lint/rule_mechanisms.json`:
  `roles-sonnet-is-the-floor`, `roles-override-carries-expiry`, `roles-remove-override-file`,
  `shared-trees-install-refusal-hook`, `verification-never-waiter-loop` and
  `building-memory-never-only-home`.
- `shared-trees-no-destructive-git` stays as the reminder `No destructive git.`
- 21 rows move from `unmechanized` to `judgment`: 15 in `CLAUDE.md` and 6 in
  `output-styles/shiv-stylisms.md`. The re-kind covers every row in the map, not only `CLAUDE.md`.
  `lint/rule_audit.py` gains the kind and pins the count: `JUDGMENT_EXPECTED` is 21.
  `UNMECHANIZED_EXPECTED` falls from 75 to 54.
- `CLAUDE.md` falls from 17175 to 16292 bytes.

The interview lane, MEASURED on branch `claude-md-shrink-2` against main (93a416f):

- Three more rules lose prose, anchor and row: `roles-workers-never-spawn`, `git-wait-for-required-checks` and `git-draft-until-reviewed`. Two more shrink: `roles-sonnet-is-the-default` and `shared-trees-no-machine-wide-kill`.
- Three rows move to `unmechanized`: `roles-sonnet-is-the-default`, `verification-recovery-not-gated-on-own-state` and `reports-no-report-when-nothing-landed`. `UNMECHANIZED_EXPECTED` is 57. `RULE_FLOOR` is 98.
- `CLAUDE.md` falls from 16292 to 15636 bytes.

## Why not all 30

On main, 30 rules in the root `CLAUDE.md` named a guard or gate. After both lanes, 9 are deleted, 3 shrink, and 18 stay.
`CLAUDE.md` loads in every repo. A gate that is only a test or a CI step in this repo enforces nothing in another repo.
Several guards cover only part of their sentence. The first lane sent 23 rules to the owner for a ruling on each. See the interview ruling.
`RULE_FLOOR` in `lint/rule_audit.py` is the anchor count: 101 after the first lane, 98 after the interview. Its own comment says to update it when a rule is removed on purpose.

## The outcome, and what protects it now

Each deleted rule protected one act. A guard or gate still refuses or checks it:

- Sonnet floor for agents: the `subagent-model-floor` guard rule.
- Cap override expiry: the `subagent-model-cap` guard rule and the watch in `hooks/config_watch.py`. Removal before expiry has no check. See hole 1.
- Refusal hook installed: `settings.json` wires `hooks/guard.py` under `PreToolUse`.
- No waiter loop: the `waiter` guard rule.
- Memory never the only home: `hooks/ruling_home.py`.
- Unlisted agents run Sonnet: the setting `env.CLAUDE_CODE_SUBAGENT_MODEL` in `settings.json`, checked by `hooks/test_wrappers.py`.
- Workers never spawn: the setting `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` in `settings.json`. Checked by `hooks/test_wrappers.py`. See hole 11.
- Wait for required checks: the `merge-checks` guard rule refuses a merge while a check is pending or red. Nothing makes a session wait after a push before it reports.
- Open every PR as a draft: the `draft-pr` guard rule, for the create command only. See hole 12.

## Holes, named

1. The watch reverts the cap override only at expiry. No text now tells an agent to remove the file before then. Debt: `override-removal-unreminded`, no early-removal reminder.
2. An agent now meets the `_subagentCapUntil` field only in the revoke message of `hooks/config_watch.py`, after a bad write. Debt: `cap-until-field-taught-late`, the field is taught late.
3. Closed: the `unmechanized` line in the `lint/rule_audit.py` docstring no longer overlaps `judgment`.
4. These 14 rules stay as prose, unchanged by the interview: `outcomes-mechanize-rules`, `roles-opus-override-guarded`, `roles-third-try-steps-up`, `git-never-discard-output`, `git-remedy-never-names-target`, `git-slug-then-claim-number`, `git-cite-by-id`, `verification-trust-guard-after-red`, `verification-cry-wolf-guard-is-spent`, `verification-report-unknown-reads`, `building-allow-list-is-the-constant`, `building-scanner-respects-strings`, `reports-order-of-labels`, `reports-done-format`.
5. A move from `unmechanized` to `judgment` takes a rule off the list of rules that still wait for a check. Only the 8-word reason floor and the two pins in one commit stand in the way. Debt: `judgment-exits-debt-count`, a re-kind leaves the waiting list.
6. A measured time table (deferred item measured-time-table) may let a check judge `style-no-unmeasured-estimate`. Debt: `estimate-rule-may-be-checkable`, the time table may give it a check.
7. A repo that raises spawn depth gets no prompt to record the risk. Debt: `nesting-risk-unrecorded`, no prompt to record the risk.
8. `report_gate` checks only `D<n>`-style ids, so a slug id passes with no gloss check. Debt: `slug-cite-gloss-unchecked`, slug cites have no gloss check.
9. `report_gate` returns early when nothing landed, so it cannot see a report on that turn. Debt: `report-on-empty-turn-unchecked`, no check sees a report on an empty turn.
10. `output-write-in-ste` is now the plain-prose rule (decision plain-prose-lint, the STE lint turned plain-prose lint). Its gate still judges file writes only. Debt: `plain-prose-writes-only`, replies and briefs are unchecked.
11. The two deleted rules took their gate rows, which checked the agent model and spawn depth in `settings.json`. Two cases in `hooks/test_wrappers.py` now check that the model is "sonnet" and the depth is "1", so no check is lost.
12. No guard reads a command that marks a PR ready. The kept rule `git-integration-branch-merge` still says only the integration PR goes ready. The clause "only after review" has no text. Debt: `pr-ready-unguarded`, nothing guards marking a PR ready.
13. Nothing makes a session wait for checks after a push before it reports. `hooks/ci_wake.py` starts no wait on a push. Debt: `push-report-before-checks`, no wait after a push.
14. The map no longer ties the `merge-checks`, `draft-pr` and `pointer-head` guard rules to a rule. A guard deleted together with its tests now passes `lint/rule_audit.py`. Debt: `guard-untied-from-rule-map`, three guards have no row.

Kind: process
Home: rule:outcomes-mechanize-rules
