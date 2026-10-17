# CLAUDE.md drops the prose of a rule that a guard or gate enforces

## Ruling

Owner, 2026-10-16 23:53 CDT and 2026-10-17 00:40 CDT:

- Delete the prose of each guard or gate rule.
- Keep a reminder of 3 words or fewer where agents hit the guard often.
- Never reword a kept rule.
- Re-kind an `unmechanized` rule to `judgment` when its reason already says no check can judge it. `judgment` means no exact check can judge the rule. A model hook that comments on a reply is not an exact check. A reason that says no check reads the rule yet stays `unmechanized`.
- Owner, 2026-10-17 02:28 CDT, "Merge it": the second lane scored zero net value at review round 3. Its one opened hole (hole 14) comes from the deleted rules themselves.

Owner interview, 2026-10-17 (00:44 to 01:55 CDT), per rule:

- `roles-sonnet-is-the-default`: delete only the sentence "An unlisted agent runs Sonnet, and that needs no word." Row kind `unmechanized`.
- `roles-workers-never-spawn`, `git-wait-for-required-checks`, `git-draft-until-reviewed`: delete prose, anchor and row.
- `shared-trees-no-machine-wide-kill`: keep only the two sentences on killing and restarting. Keep anchor and row.
- `verification-recovery-not-gated-on-own-state` and `reports-no-report-when-nothing-landed`: keep the text. Row kind `unmechanized`.
- `speak-cite-id-plus-gloss`: keep.
- `output-write-in-ste`: separate lane.
- Kept as prose: `outcomes-mechanize-rules`, `roles-opus-override-guarded`, `roles-third-try-steps-up`, `git-never-discard-output`, `git-remedy-never-names-target`, `git-slug-then-claim-number`, `git-cite-by-id`, `verification-trust-guard-after-red`, `verification-cry-wolf-guard-is-spent`, `verification-report-unknown-reads`, `building-allow-list-is-the-constant`, `building-scanner-respects-strings`, `reports-order-of-labels`, `reports-done-format`.

Precedent: `a-rule-with-no-gate-leaves-claude-md`.

Why not all 30 rules: `CLAUDE.md` loads in every repo, and a gate that is only a test or a CI step here enforces nothing in another repo. Several guards cover only part of their sentence. `RULE_FLOOR` in `lint/rule_audit.py` is the anchor count (98). Update it when a rule is removed on purpose.

What still protects each deleted rule:

- Sonnet floor for agents: the `subagent-model-floor` guard rule.
- Cap override expiry: the `subagent-model-cap` guard rule and the watch in `hooks/config_watch.py`.
- Refusal hook installed: `settings.json` wires `hooks/guard.py` under `PreToolUse`.
- No waiter loop: the `waiter` guard rule.
- Memory never the only home: `hooks/ruling_home.py`.
- Unlisted agents run Sonnet, and workers never spawn: `env.CLAUDE_CODE_SUBAGENT_MODEL` and `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` in `settings.json`, checked by `hooks/test_wrappers.py`.
- Wait for required checks: the `merge-checks` guard rule refuses a merge while a check is pending or red.
- Open every PR as a draft: the `draft-pr` guard rule, for the create command only.

## Holes, named

Debts: `override-removal-unreminded` (no early-removal reminder for the cap override file), `cap-until-field-taught-late` (an agent meets `_subagentCapUntil` only in the revoke message), `judgment-exits-debt-count` (a re-kind leaves the waiting list), `estimate-rule-may-be-checkable` (the time table may give `style-no-unmeasured-estimate` a check), `nesting-risk-unrecorded` (no prompt to record the risk of a raised spawn depth), `slug-cite-gloss-unchecked` (slug cites have no gloss check), `report-on-empty-turn-unchecked` (no check sees a report on an empty turn), `plain-prose-writes-only` (replies and briefs are unchecked by the plain-prose rule, `plain-prose-lint`), `pr-ready-unguarded` (nothing guards marking a PR ready), `push-report-before-checks` (no wait after a push), `guard-untied-from-rule-map` (the `merge-checks`, `draft-pr` and `pointer-head` guard rules have no row).

Kind: process
Home: rule:outcomes-mechanize-rules
