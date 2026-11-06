# A lane brief's Done check gets a refuter read before the send

## The ruling

Ruling: owner, 2026-11-06, the owner's waiting-page item 284 c. The owner's waiting-page item 282 b, same day, fixes the word as "refuter". The owner's waiting-page item 289, 2026-11-06 13:59 CST, says "for now let's do sonnet for all": the refuter runs Sonnet.

- Each lane brief carries one `Done check:` line. It names the one check that proves the ask met.
- Before the send goes through, the check refuter reads that line once, blind. It asks whether the check could pass while the ask stays unmet.
- A gap refuses the send under rule `check-refuter`. The refusal gives the case.
- An unknown refuses the send. A met answer lets it through.

## The check

Check: `hooks/check_refuter.py`, the one home of the check refuter. `hooks/call_judge.py` calls it at a `send_message`.

- Trigger: a `send_message` whose first non-blank line starts `Lane brief: <step>. Topic: <topic>.` Other messages make no model call and do not load the module.
- Done check line: the brief's line that names the check. These forms count:
  - plain: `Done check: <check>`
  - bold: `**Done check:** <check>`
  - bold, colon outside the bold: `**Done check**: <check>`
  - bullet: `- Done check: <check>`
  - lowercase: `done check: <check>`
  - with a proof note: `Done check (proof): <check>`
  - heading: a `## Done check` heading, with the check on the next line.
- A line inside a fenced code block never counts.
- A `<...>` placeholder counts as no line. The send is refused the same way.
- Input: the step's title and why, read from `roadmap/data/steps/<step>.json` on the local record-branch ref, by one `git show`. The Done check line. Nothing else: no brief body, no diff.
- Model: one call through `REFUTER_MODEL`, one named setting, value `sonnet`.
- Timing: the model call waits at most `REFUTER_TIMEOUT`, 45 s. The git read waits at most `GIT_TIMEOUT`, 20 s. The worst wait is 65 s, inside the 70 s `call_judge` hook timeout in `settings.json`.
- Bar for a gap: flag only when a worker following the brief could realistically pass the check with the ask unmet.
- Answers:
  - met: the send goes through.
  - gap: the send is refused. The reason is the model's case.
  - unknown: the send is refused. Causes: a model error, an odd answer, or an unreadable step (a missing ref, file, title or why). The reason names the fetch command: `git fetch origin +refs/heads/<record branch>:refs/remotes/origin/<record branch>`.
- No Done check line, or a placeholder only: the send is refused, with no model call.
- Override: the owner override (`docs/decisions/owner-override.md`) lifts each refusal: a gap, an unknown, or a missing line.

## Limits

- The refuter reads text. It never runs the check. It judges whether the check could pass while the ask stays unmet.
- A met answer is one model's read. The lane's own check still proves the work.
- Unknown refuses. An unreadable step blocks a brief. It never passes one.
- The step-close site is not in this change. It follows once PR #1317 (step-done-needs-check, which makes a step's done state need its check) merges. Then triage runs one command at step close. The command writes a dated refuter line into the step note. The roadmap build only reads that line.
- Opus for some refuters is open. Lane `debate-model-tiers` decides it. Owner item 289 keeps Sonnet for all until then.

## Guard need

Risk kind: likely risk. Per rule `building-guard-needs-incident`, a guard names the mistake it stops.

- Mistake: a lane marks its work done by a check that misses the ask. The check passes, and the ask is unmet.
- Harm: the step reads done while the ask is unmet.

## Why

- A check that misses the ask gives a false done.
- The refuter reads the check against the ask before the lane starts. The miss shows at send time.
- Protects: a step's done state means that its ask is met.

## Cost

- Per lane brief: one Sonnet call and one `git show` of the step file from the record-branch ref.
- Per refusal: one `guard.log` line, written by `guard_core.refuse()`, as every refusal does.
- Per other `send_message`: no model call and no module load. The `call_judge` matcher now includes `send_message`, so each one starts the hook process.
- No other file, timer or log.

## Done check

The cases in `hooks/test_check_refuter.py` are the Done check. They must cover:

- A gap refuses, with the model's case.
- A met answer sends.
- A model error, an odd answer and an unreadable step each refuse as unknown, never met. The unknown reason names the fetch command.
- A brief with no `Done check:` line, or only a `<...>` placeholder, refuses, with no model call.
- Each accepted form counts, and a line inside a fenced block does not.
- Any other `send_message` makes no model call.

That file lands with lane `check-line-reader`.

Kind: build
Plan: docs/decisions/check-refuter.md#the-ruling (all)
