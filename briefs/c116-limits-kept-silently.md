# Brief: c116, a session keeps to a limit without narrating it

Repo: shivinate7/claude-settings, from main b031394f. One lane: builder (sonnet), then reviewer (sonnet).

## Task
Sessions narrate limits and checks that passed ("staying under the 15-line cap", "rule X holds"). The owner wants silence unless the limit blocks the work or changes the plan.
- Add one rule to `output-styles/shiv-stylisms.md`: keep to a limit or rule silently; name it only when it blocks the work or changes the plan. A skipped step or dropped item is still said (building-never-drop-item-silently).
- Teach the reply judge (`hooks/reply_judge.py`, model from agent-model-cap) to flag a reply that narrates a check that passed or a limit kept. Add its cases to the judge's case file.
- Keep the rule in the output style only; do not add it to CLAUDE.md (replies to the owner live in the style).

## Rulings
- shiv, Oct 27 (step c116): the rule above.
- verification-cry-wolf-guard-is-spent: a reply that says a limit blocked the work, or names a dropped item, must pass.

## Failure classes
- A flag on "tests pass" as a result line in Done (a result is not narration of a kept limit).
- A judge case file that only holds passing cases.

## Check that proves it done
New judge cases, red on main b031394f (the judge passes the narrating reply) and green on the branch, through the judge's offline case runner (hooks/case_runner_test.py or the judge's own test). Also lint/rule_audit.py, lint/hook_catalog.py --check, bin/ste-changed origin/main.

## Report
At most 15 lines: PR, head, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.
