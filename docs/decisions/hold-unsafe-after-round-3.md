# Hold a guard or check change whose net safety value is negative after round 3

## Ruling

Owner, 2026-10-15 12:00 CDT. The owner's words:

- `i basically don't want worse things merging to main, but if something has made an improvement to main and it's just still unfinished then it's still good to merge to main (so say the work was 6 safety holes from before it started to now becoming 3 after the rounds, that's good to merge to main)`
- `considering AI is judging this, we can have it be that the evaluation is moreso semantic value like if our net expected value is positive the change is allowed`

`roles-review-cap-three` (a change gets three review rounds, CLAUDE.md) holds the rule that follows. This record holds what that rule lacks:

- The judgment is semantic.
- The owner's grant can allow work on a held change. A merge still needs zero or positive net value.
- A main ask that the change turns into a refusal is a safety hole closed.
- Owner, 2026-10-15 13:40 CDT: a held change that is red in CI gets no red-CI split. A change that is not held keeps the split (red CI is split, not a safety hole).
- Owner, 2026-10-17 11:56 and 12:53 CDT: a change that only deletes and adds nothing gets one review round. It skips rounds 2 and 3 and the net-value test. A delete-only change opens no safety hole unless it removes a guard or check, which round 1 must judge. The owner gave no other reason. If round 1 finds a safety hole Claude could hit in normal work, the normal path applies. A change that adds anything takes the normal path.
- Owner, 2026-10-25 14:25 CDT, PR 571 (ios-ship, one shared tool to ship iOS apps): the net-value test is not owed when the guard edits only add coverage for a new tool and loosen nothing.
- Owner, 2026-10-29 16:33 CDT, option a: a change with zero or positive net value merges on green. Only a change with negative net value is held. The owner's words: `i thought its zero and greater not just positive that r permitted`.
- Owner, 2026-11-03 22:24 CST, Cockpit item 203 a, in every repo: a small fix to a round's finding gets one short read, a fix check, and then merges. A guard or check change still owes round 3 before it merges (item 402 a, owner, 2026-11-08 06:08 CST). Incident: degen page item 83, where five PRs were held about 2 hours (degen D10, a record in that repo, not read here). The definition:
  - A fix check is a fresh reviewer that reads only `git diff <reviewed-head>..<head>`. After a merge from main, it reads only `git diff origin/main...<head>` for size (item 401 a, owner, 2026-11-08 06:08 CST). The guard question reads the same diff (claude-settings coordinator, 2026-11-07 23:15 CST, lane batch63-lint-a; not the owner's words). It confirms the diff fixes the named finding and adds nothing else.
  - PASS: the head merges on green, with no further round, unless a guard or check change still owes round 3 (item 402 a, owner, 2026-11-08 06:08 CST).
  - FAIL, or a diff wider than the finding: the fix starts a new lane at round 1.
  - FAIL also when the diff touches a guard or check path (the list below) while the review record says `Guard or check: no`. The merge tool reads no diff, so a wrong `no` would skip the net-value test (owner, 2026-11-05 07:45 CST, typed "go" in the lane). After a merge from main, this FAIL reads the same `git diff origin/main...<head>` (claude-settings coordinator, 2026-11-07 23:15 CST, lane batch63-lint-a; not the owner's words). Main's content is already reviewed on main.
  - A fix check is not a review round. It runs on sonnet, on every PR (owner item 444 a, 2026-11-08 15:04 CST). The orchestrator sets sonnet per spawn, and the merge tool refuses a fix-check record that names another model. Its brief starts with the `Fix check` marker and carries no `Round N of 3` marker.
  - Owner item 271 b, 2026-11-05 21:31 CST: a fix check may follow a FAIL in any round. The design-reviewer hold (decision `pr-review-record`) stays.
  - A passing fix check is the review of the new head for a change that changes no guard or check. For a guard or check change, round 3 with the net-value test still runs, even when a fix check passes before it (item 402 a, owner, 2026-11-08 06:08 CST). A fix check does not repeat the net-value test (owner, 2026-11-05 08:41 CST, typed in the lane; page item 232 a). A guard or check change keeps the net value that round 3 gave it.
- A change changes a guard or check when it edits one of these. The list is the orchestrator's brief, not an owner grant. Test files alone never count (owner, 2026-10-15 22:39 and 22:55 CDT).
  - A guard: any hook that can refuse or ask, with its wiring and prompt-type guards in `settings.json`. Also any `allow`, `deny` or `ask` entry under `permissions` in `settings.json`, and any `tools` or `disallowedTools` line in `agents/*.md` frontmatter. Examples: `hooks/guard*.py`, `hooks/rm_prompt_answer.py`, `githooks/`.
  - A check: any check that can fail CI or the merge. Examples: `.github/workflows/`, `actions/*`, `lint/` checks, `merge/` checks, `hooks/mutate_*.py`.

Why: the owner does not want worse changes on main, and does want partial progress merged. A change that takes main from 6 safety holes to 3 merges. A change that changes no guard or check scores zero by construction, so it skips the test. Holes that main already has do not count against a change. Only the safety holes a change opens count against it, and the safety holes it closes count for it. Protected outcome: no merge leaves main worse on net, and no open finding that Claude is likely to hit stays out of sight.

Kind: process
Home: rule:roles-review-cap-three
