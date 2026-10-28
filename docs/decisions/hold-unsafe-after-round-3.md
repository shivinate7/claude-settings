# Hold a guard or check change whose net safety value is not positive after round 3

## Ruling

Owner, 2026-10-15 12:00 CDT. The owner's words:

- `i basically don't want worse things merging to main, but if something has made an improvement to main and it's just still unfinished then it's still good to merge to main (so say the work was 6 safety holes from before it started to now becoming 3 after the rounds, that's good to merge to main)`
- `considering AI is judging this, we can have it be that the evaluation is moreso semantic value like if our net expected value is positive the change is allowed`

`roles-review-cap-three` (a change gets three review rounds, CLAUDE.md) holds the rule that follows. This record holds what that rule lacks:

- The judgment is semantic.
- The owner's grant can allow work on a held change. A merge still needs positive net value.
- A main ask that the change turns into a refusal is a safety hole closed.
- Owner, 2026-10-15 13:40 CDT: a held change that is red in CI gets no red-CI split. A change that is not held keeps the split (red CI is split, not a safety hole).
- Owner, 2026-10-17 11:56 and 12:53 CDT: a change that only deletes and adds nothing gets one review round. It skips rounds 2 and 3 and the net-value test. A delete-only change opens no safety hole unless it removes a guard or check, which round 1 must judge. The owner gave no other reason. If round 1 finds a safety hole Claude could hit in normal work, the normal path applies. A change that adds anything takes the normal path.
- Owner, 2026-10-19 00:07 CDT, `Merge on zero`: a change whose only lifts need an override the owner typed (`owner-override`, an owner override) scores zero and merges on green.
- Owner, 2026-10-25 14:25 CDT, PR 571 (ios-ship, one shared tool to ship iOS apps): the net-value test is not owed when the guard edits only add coverage for a new tool and loosen nothing.
- A change changes a guard or check when it edits one of these. The list is the orchestrator's brief, not an owner grant. Test files alone never count (owner, 2026-10-15 22:39 and 22:55 CDT).
  - A guard: any hook that can refuse or ask, with its wiring and prompt-type guards in `settings.json`. Also any `allow`, `deny` or `ask` entry under `permissions` in `settings.json`, and any `tools` or `disallowedTools` line in `agents/*.md` frontmatter. Examples: `hooks/guard*.py`, `hooks/rm_prompt_answer.py`, `githooks/`.
  - A check: any check that can fail CI or the merge. Examples: `.github/workflows/`, `actions/*`, `lint/` checks, `merge/` checks, `hooks/mutate_*.py`.

Why: the owner does not want worse changes on main, and does want partial progress merged. A change that takes main from 6 safety holes to 3 merges. A change that changes no guard or check scores zero by construction, so the test would park it for wording nits. Holes that main already has do not count against a change. Only the safety holes a change opens count against it, and the safety holes it closes count for it. Protected outcome: no merge leaves main worse on net, and no open finding that Claude is likely to hit stays out of sight.

Kind: process
Home: rule:roles-review-cap-three
