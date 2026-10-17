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

The rule that follows:

- After round 3, a change that changes a guard, gate or check gets the net-value test. The round-3 reviewer judges its net safety value against main: holes closed against holes opened, weighted by expected harm. The judgment is semantic.
- Positive net value merges on green. Every open finding becomes a named limit and a debt, for every change.
- A change with zero or negative net value is held. It is dropped from the batch, so the rest merges green. It is parked: it gets no fix lane and no more work until the owner decides.
- The owner's word can allow work on a held change. A merge still needs positive net value.
- Owner ruling, 2026-10-15 13:40 CDT: a held change that is red in CI gets no red-CI split.
- The red-CI split in `review-cap-red-ci` (red CI is split, not a hole) still applies to changes that are not held.
- A safety hole is a guard, gate or check that lets through an act that main refuses or asks about. For a guard hook (`hooks/guard*.py`), it counts only if Claude could write the act by mistake or from a misread task (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker).
- A main refusal that the change turns into an ask is a hole opened. A main ask that the change turns into a refusal is a hole closed.

## Why

The owner does not want worse changes on main. He does want partial progress merged. A change that takes main from 6 safety holes to 3 merges. A change that changes no guard, gate or check scores zero by construction, so the test would park it for wording nits.

Holes that main already has do not count against a change. Every guard on main has known gaps. Only the holes a change opens count against it, and the holes it closes count for it.

Protected outcome: no merge leaves main worse on net. No open gap stays out of sight.

## Holes, named

- No check measures net safety value. The call is the round-3 reviewer's judgment. Debt: `safety-hole-test-is-judgment`.
- No check makes the orchestrator read the round-3 line `Net safety value:` before a merge. Debt: `safety-line-unread-at-merge`.
- No check reads the trigger judgment, whether a change changes a guard, gate or check. Debt: `trigger-call-unchecked`.
- The trigger omits the `settings.json` env caps `CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, and the `model:` and `effort:` lines in `agents/*.md`. They enforce `roles-sonnet-is-the-ceiling` (Sonnet is the agent ceiling) and keep workers from spawning. Debt: `trigger-omits-agent-caps`.
- Some cites lacked a gloss. No check requires one. Debt: `cites-lack-gloss-unchecked`.

Debts:

- `safety-hole-test-is-judgment`: no check measures net value.
- `safety-line-unread-at-merge`: no check reads the round-3 line.
- `hold-own-hole-unrecorded`: where a held change records its hole.
- `trigger-call-unchecked`: no check reads the trigger.
- `trigger-omits-agent-caps`: the trigger omits the agent caps.
- `cites-lack-gloss-unchecked`: no check requires a cite gloss.

Kind: process
Home: rule:roles-review-cap-three
