# CLAUDE.md drops the prose of a rule that a guard or gate enforces

## The question

How short can the root `CLAUDE.md` get, when a guard or gate already enforces a rule?

## Ruling

Owner ruling, 2026-10-16 23:53 CDT. In short:

- Delete the prose of each guard or gate rule.
- Keep a reminder of 3 words or fewer where agents hit the guard often.
- Re-kind an `unmechanized` rule to `judgment` when its reason already says no check can judge it.
- Never reword a kept rule.

Precedent: `a-rule-with-no-gate-leaves-claude-md` (a rule the owner took off the gate leaves `CLAUDE.md` too).

## What landed, MEASURED on branch `claude-md-shrink` (a1655ad) against main

- Six rules lose their prose, anchor and row in `lint/rule_mechanisms.json`:
  `roles-sonnet-is-the-floor`, `roles-override-carries-expiry`, `roles-remove-override-file`,
  `shared-trees-install-refusal-hook`, `verification-never-waiter-loop` and
  `building-memory-never-only-home`.
- `shared-trees-no-destructive-git` stays as the reminder `No destructive git.`
- 15 rows move from `unmechanized` to `judgment`. `lint/rule_audit.py` gains the kind and pins
  the count: `JUDGMENT_EXPECTED` is 15. `UNMECHANIZED_EXPECTED` falls from 75 to 60.
- `CLAUDE.md` falls from 17175 to 16292 bytes.

## Why only 6 of 30

On main, 30 rules in the root `CLAUDE.md` name a guard or gate. 6 are deleted, 1 shrinks, and 23 stay.
`CLAUDE.md` loads in every repo. A gate that is only a test or a CI step in this repo enforces nothing in another repo.
Several guards cover only part of their sentence. Those 23 rules stay until the owner rules on each.
`RULE_FLOOR` in `lint/rule_audit.py` moves from 98 to 101, the new anchor count. Its own comment says to update it when a rule is removed on purpose.

## The outcome, and what protects it now

Each deleted rule protected one act. A guard or gate still refuses or checks it:

- Sonnet floor for agents: the `subagent-model-floor` guard rule.
- Cap override expiry: the `subagent-model-cap` guard rule and the watch in `hooks/config_watch.py`. Removal before expiry has no check. See hole 1.
- Refusal hook installed: `settings.json` wires `hooks/guard.py` under `PreToolUse`.
- No waiter loop: the `waiter` guard rule.
- Memory never the only home: `hooks/ruling_home.py`.

## Holes, named

1. The watch reverts the cap override only at expiry. No text now tells an agent to remove the file before then. Debt: `override-removal-unreminded`, no early-removal reminder.
2. An agent now meets the `_subagentCapUntil` field only in the revoke message of `hooks/config_watch.py`, after a bad write. Debt: `cap-until-field-taught-late`, the field is taught late.
3. The `unmechanized` line in the `lint/rule_audit.py` docstring still says "genuinely cannot be checked by a machine". That overlaps `judgment`. Debt: `unmech-doc-overlaps-judgment`, the docstring overlaps the new kind.
4. These 23 rules stay as prose, each unsure: `outcomes-mechanize-rules`, `roles-sonnet-is-the-default`, `roles-opus-override-guarded`, `roles-workers-never-spawn`, `roles-third-try-steps-up`, `shared-trees-no-machine-wide-kill`, `git-wait-for-required-checks`, `git-never-discard-output`, `git-remedy-never-names-target`, `git-slug-then-claim-number`, `git-cite-by-id`, `git-draft-until-reviewed`, `verification-trust-guard-after-red`, `verification-cry-wolf-guard-is-spent`, `verification-recovery-not-gated-on-own-state`, `verification-report-unknown-reads`, `building-allow-list-is-the-constant`, `building-scanner-respects-strings`, `speak-cite-id-plus-gloss`, `output-write-in-ste`, `reports-order-of-labels`, `reports-done-format`, `reports-no-report-when-nothing-landed`.

Kind: process
Home: rule:outcomes-mechanize-rules
