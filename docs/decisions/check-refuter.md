# A lane brief's Done check gets a refuter read before the send

## The ruling

Ruling: owner, 2026-11-06, the owner's waiting-page item 284 c. The owner's waiting-page item 282 b, same day, fixes the word as "refuter".

- Each lane brief carries one `Done check:` line. It names the one check that proves the ask met.
- Before the send goes through, the check refuter reads that line once, blind. It asks whether the check could pass while the ask stays unmet.
- A gap refuses the send under rule `check-refuter`. The refusal gives the case.
- An unknown refuses the send. A met answer lets it through.

Owner note: some refuters should run Opus. Lane `debate-model-tiers` decides which.

## The check

Check: `hooks/check_refuter.py`, the one home of the check refuter. `hooks/call_judge.py` calls it at a `send_message`.

- Trigger: a `send_message` whose first non-blank line starts `Lane brief: <step>. Topic: <topic>.` Other messages make no model call and do not load the module.
- Input: the step's title and why, read from `roadmap/data/steps/<step>.json` on the local record-branch ref. The brief's `Done check:` line. Nothing else: no brief body, no diff.
- Model: one call through `REFUTER_MODEL`, one named setting, value `sonnet`. Its wait is `REFUTER_TIMEOUT`, under the `call_judge` hook timeout in `settings.json`.
- Answers:
  - met: the send goes through.
  - gap: the send is refused. The reason is the model's case.
  - unknown: the send is refused. Causes: a model error, an odd answer, or an unreadable step (a missing ref, file, title or why).
- No `Done check:` line: the send is refused, with no model call.
- Override: the owner override (`docs/decisions/owner-override.md`) lifts each refusal: a gap, an unknown, or a missing line.

## Limits

- The refuter reads text. It never runs the check. It judges whether the check could pass while the ask stays unmet.
- A met answer is one model's read. The lane's own check still proves the work.
- Unknown refuses. An unreadable step blocks a brief. It never passes one.
- The step-close site is not in this change. It follows once PR #1317 (step-done-needs-check, which makes a step's done state need its check) merges. Then triage runs one command at step close. The command writes a dated refuter line into the step note. The roadmap build only reads that line.
- The model tier is open. Some refuters should run Opus, and lane `debate-model-tiers` decides. Until it rules, `REFUTER_MODEL` stays `sonnet`.

## Guard need

Risk kind: likely risk. Per rule `building-guard-needs-incident`, a guard names the mistake it stops.

- Mistake: a lane marks its work done by a check that misses the ask. The check passes, and the ask is unmet.
- Harm: the step reads done while the ask is unmet.

## Why

- A check that misses the ask gives a false done.
- The refuter reads the check against the ask before the lane starts. The miss shows at send time.
- Protects: a step's done state means that its ask is met.

## Cost

- Per lane brief: one Sonnet call, and one read of the step file from the record-branch ref. The git process count is unmeasured until the module lands.
- Per refusal: one `guard.log` line, written by `guard_core.refuse()`, as every refusal does.
- Per other `send_message`: no model call and no module load. The `call_judge` matcher now includes `send_message`, so each one starts the hook process.
- No other file, timer or log.

## Done check

The cases in `hooks/test_check_refuter.py` are the Done check. They cover:

- A gap refuses, with the model's case.
- A met answer sends.
- A model error, an odd answer and an unreadable step each refuse as unknown, never met.
- A brief with no `Done check:` line refuses, with no model call.
- Any other `send_message` makes no model call.

That file lands with lane `check-line-reader`.

Kind: build
Plan: docs/decisions/check-refuter.md#the-ruling (all)
