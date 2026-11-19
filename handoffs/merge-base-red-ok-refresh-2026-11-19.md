# Handoff: lane merge-base-red-ok-refresh, 2026-11-19

- Slug: merge-base-red-ok-refresh. Session: session_013NEJKzyVUbeFsmoQeuaUP2. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Step: allow-merge-base-red-ok.
- Work branch: `allow-merge-base-red-ok`, head `08eeacd4d150356925ed86b0840131899040b49b` (on origin). Local worktree: `.claude/worktrees/merge-base-red-ok-refresh` (cloud, lost with the container).
- Open PR: #3097 (allow-merge-base-red-ok), open, ready (not draft), head `08eeacd4d`, base was main `2a388ccd9`; GitHub reads it as conflicting (dirty) now that main moved. Opened ready by the owner before this lane. This lane never flipped it.

## Done

- Run 43375520417 red: #3097's own fault. Test `test_the_repo_settings_json_has_no_merge_allow_rule` (merge/test_merge.py) forbids any `--confirm` merge rule in settings.json; the PR added one. Not main's red.
- `ae55b6c45`: plain merge of main (clean). `5e921534c`: test re-pointed to `test_the_repo_settings_json_has_one_merge_allow_rule_and_no_other` (red on `2a388ccd9`, green on the branch; `Red-run:` trailer), two sentences in docs/decisions/auto-mode-owner-acts.md rewritten. `08eeacd4d`: comment fix after the code check's narration rule failed on a date (job 132280109424).
- Round 1 review (reviewer haiku, on `5e921534c`): FAIL. No review record exists at the current head. The old record and lane lint (PASS) are bound to `33f1088ff`, so both are stale.

## Round 1 findings (all unfixed)

1. settings.json:14 glob matches any `--base-red-ok <reason>` merge, and absorbs `--undo-check-unknown-ok`. Main asks on both. Cloud's merge/cloud_allow.json already allows `merge * --confirm *`.
2. The `~/.claude/bin/merge` spelling and no-`--head` forms still prompt (false alarm). The decision sentence "allowed by one permissions.allow rule" is wrong in the cloud.
3. The trim of `--base-red-ok` from Never-covers in settings.json lines 60-61 and hooks/test_auto_mode_allow.py: now ruled by own-786-c. The 2026-11-12 23:42/23:44 CST ruling cited in commit `33f1088ff` is in no record. Do not cite it.
4. The test asserts the string only. Add glob-match cases: revert form matches; no `--head`, no reason, `--undo-check-unknown-ok` refused. Comment at merge/test_merge.py:13506 says "every other merge act still does" prompt, which is false.
5. Stale: merge/test_merge.py:13424 and install.sh:1056 say a local settings.json gets no merge rule.
6. Decision text calls it the "red-main revert flag"; the glossary term is "reason flag" (GLOSSARY.md:31), and fix batches use it too.

## Unfinished and next step

- Owner pick on page item 791 (scope): 1 keep as written (marked widening), 2 narrow first (a merge-tool check that the PR reverts the breaking merge; triage recommends it), 3 drop the rule and restore both Never-covers sentences. Unanswered when this lane stopped.
- After the pick: fix findings 1 to 6 in one push, merge main again (plain merge, no rebase, no force push; take main's docs/records.md in its own command), post a review record at the new head, run round 2, then lane lint (needs a draft for the touched-tests run; the ruling draft-until-reviewed does not cover flipping a ready PR back to draft, so ask), then hand to runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) with "Merge after: none".

## Rulings held

- Owner pick 786 c, 2026-11-13 19:21 CST (ruling own-786-c-base-red-ok-settings): add the rule to settings.json, re-point the test red then green, rewrite the decision sentences that say entries never cover `--base-red-ok` in the same PR, get a guard review. Relayed by the page writer session_013NEJKzCzoWhfP8FMCPtQU6. I could not read answers/pick-base-red-ok-allow-rule from the cloud: unknown.
- The brief: never merge, never close another PR, no check-lifting flag, tell the coordinator before any draft or ready flip.

## Refused acts

- None refused by a guard to this lane. Hook stops forced rewrites of my reports (report shape, model names, departs-from line). One SendMessage to a session id was refused; the MCP send_message was used.

## Agents

- Reviewer `a21e14020c5f993a6`, role reviewer, model haiku, worktree gone. Report: FAIL at `5e921534c`. No other agents.
- Builder for the edits: this lane itself (sonnet).

## Messages sent

- Page writer: scope and trim question (item 791 filed). Coordinator: finding summary and CI cause.
