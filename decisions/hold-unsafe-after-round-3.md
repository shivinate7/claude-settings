# Hold a guard, gate or check change whose net safety value is not positive after round 3

## The question

After review round 3, does a change merge or get held?

## Trigger

A change changes a guard, gate or check when it edits one of these:

- A guard: any hook that can refuse or ask, with its wiring and prompt-type gates in `settings.json`. Also any `allow`, `deny` or `ask` entry under `permissions` in `settings.json`, and any `tools` or `disallowedTools` line in `agents/*.md` frontmatter. Examples: `hooks/guard*.py`, `hooks/rm_prompt_answer.py`, `githooks/`.
- A gate or check: any check that can fail CI or the merge. Examples: `.github/workflows/`, `actions/*`, `lint/` checks, `merge/` checks, `hooks/mutate_*.py`.

Test files alone never count. The owner words of 2026-10-15 22:39 CDT ("should be adjusted") and 2026-10-15 22:55 CDT (option "No test change counts") set the scope. The definition above is the orchestrator's brief, not an owner word.

## Ruling

Owner ruling, 2026-10-15 12:00 CDT. The owner's words:

- `i basically don't want worse things merging to main, but if something has made an improvement to main and it's just still unfinished then it's still good to merge to main (so say the work was 6 safety holes from before it started to now becoming 3 after the rounds, that's good to merge to main)`
- `considering AI is judging this, we can have it be that the evaluation is moreso semantic value like if our net expected value is positive the change is allowed`

`roles-review-cap-three` (a change gets three review rounds, CLAUDE.md) holds the rule that follows from these words. This entry holds what that rule lacks:

- The judgment is semantic.
- The owner's word can allow work on a held change. A merge still needs positive net value.
- A main ask that the change turns into a refusal is a hole closed.
- Owner ruling, 2026-10-15 13:40 CDT: a held change that is red in CI gets no red-CI split. A change that is not held keeps the split in `review-cap-red-ci` (red CI is split, not a hole).
- Owner ruling, 2026-10-17 11:56 CDT: a change that only deletes and adds nothing gets one review round. It skips rounds 2 and 3 and the net-value test, unless round 1 finds a hole Claude could hit in normal work. Then the normal path applies. A change that adds anything takes the normal path.

## Why

The owner does not want worse changes on main. He does want partial progress merged. A change that takes main from 6 safety holes to 3 merges. A change that changes no guard, gate or check scores zero by construction, so the test would park it for wording nits.

A delete-only change opens no hole by construction, unless round 1 shows one Claude could hit. Holes that main already has do not count against a change. Every guard on main has known gaps. Only the holes a change opens count against it, and the holes it closes count for it.

Protected outcome: no merge leaves main worse on net. No open gap that Claude is likely to hit stays out of sight.

## Holes, named

Debts: `safety-hole-test-is-judgment` (no check measures net value). `safety-line-unread-at-merge` (no check reads the round-3 line). `hold-own-hole-unrecorded` (where a held change records its hole). `trigger-call-unchecked` (no check reads the trigger). `trigger-omits-agent-caps` (the trigger omits the agent caps). `cites-lack-gloss-unchecked` (no check requires a cite gloss).

Kind: process
Home: rule:roles-review-cap-three
