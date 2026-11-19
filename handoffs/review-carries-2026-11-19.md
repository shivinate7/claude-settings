# Handoff: lane review-carries-by-tree, 2026-11-19 00:30 CST

Session 8c70e9c7-82b9-52ec-b64a-59801ad7ab8d (cloud, repo shivinate7/claude-settings). Slug: `review-carries-by-tree`. Branch of this file: `archive/handoff-review-carries`. Written on the coordinator's wind-down order of 00:24 CST, relayed from the owner's 00:19 CST words. No new work started; no agent running.

## Goal
Owner priority fb-1556-6 (2026-11-14 00:25 CST): a review log on a closed PR is accepted on a replacement PR with the same tree sha, refused when the tree differs. Done as #3388 (merged). Coordinator added follow-on PRs; each is its own draft PR. I mark nothing ready and merge nothing until the coordinator says a PR is marked and its ready run is green (owner ruling 11:12 CST Nov 15, relayed).

## Open PRs (REST read 00:27 CST Nov 19)
| PR | Step | Head | State | Review log | Lane lint |
| --- | --- | --- | --- | --- | --- |
| #3481 | lint half: lane lint carries a clean merge of main | 72bccc34d778f4f47ee9de67263b3694aceb3f3e (a "Merge main" commit pushed after my hand-in at 476c8745957f; parents 476c874595 and 919261f137) | open, draft, base main | comment 6891643244 at 476c874595 (rounds 1 FAIL haiku, 2 FAIL sonnet, 3 PASS sonnet, fix check PASS sonnet, net zero) | comment 6891713613 PASS at 476c874595 |
| #3489 | `lint-carries-page-commit-no-stamp` | cef0f04675a683cdee0c2686b063c423a630999f | open, draft, base rct-lint-main-merge (stacked on #3481) | comment 6891954712 (round 1 PASS haiku, net not owed) | comment 6892213471 PASS |
| #3491 | notes docs PR (8 note lines in docs/debts/notes.md) | 93819df8fdfebda3729fef96b3b376bb2b4e35af | open, draft, base main | comment 6892001842 (docs-only, no round owed) | comment 6892280822 PASS |
| #3519 | `lint-carries-claim-after-clean-merge` (owner pick a on page item pick-carry-lint-after-claim) | d1e47a48b603c5e9ab8a9abbc9867c9ce8559f12 (clean merge of main into e8ea9c971e) | open, draft, base main (retargeted from rct-lint-page-nostamp; stacked on #3489 and #3481) | comment 6899322269 (round 1 PASS sonnet at e8ea9c971e, kept across the clean merge) | comment 6899798633 PASS (run with PR_BODY set) |

Merged since: #3388, #3448 (carry-forgives-main-merge), #3431 (line 54 rewrite), #3391 (debts and notes). Main tip when read: bd0759f83c.

## Done
- #3388, #3448 merged. #3431 and #3391 merged (by others).
- #3481, #3489, #3491, #3519 built, reviewed, linted and handed in to the coordinator with a copy to runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3).
- Page item pick-carry-lint-after-claim: owner pick a verified myself (`page_grant.py` printed `counted`, saved 2026-11-15T17:39:47Z); receipt read and filed, item closed, answer deleted. Home: decision sentences in #3519; PR 3519.

## Unfinished
- None of #3481, #3489, #3491, #3519 is merged. #3481's head moved after hand-in (a "Merge main" commit by another session): its lane lint PASS at 476c874595 may need a re-run at 72bccc34d7 (a clean merge of main is carried by the walk once #3481 itself merges; until then the old tool does not carry it).
- #3489 is stacked on #3481 (base rct-lint-main-merge); #3519 is stacked on both and based on main, so it shows the whole stack.
- Notes not yet written (one small docs PR on docs/debts/notes.md, after the merges so no reviewed head moves): (a) nothing pins a generated page made before a clean merge as not carried in tests (a mutant that ignores `merged` on the page route stays green); (b) the stacked-PR stamp-kinds read (walk reads kinds from origin/main, the claim chain from the PR base) is unpinned; (c) the docstring "at most a claim or generated page commit" reads as one commit; (d) the local `merge --lane-lint` cannot read the PR body, so the aligned check reads unknown (rc=2) unless PR_BODY is set; (e) the "clean-merge survival" bullet in pr-review-record says a one-parent commit ends the walk and its cost line omits the per-commit reads; (f) post each head's review log before pushing a fix (my mistake on #3519; the tool prints only for the live head); (g) a Record-claim commit that hand-edits only the records page counts as a claim in `claim_only` (pre-existing).
- #3481 and #3489 will hit the same two "Rules checked" alignment gaps (lanes-run-no-full-ci-job, pr-review-record) at their next head move; they need the two PR body lines `Rules checked: <record> — no change`, and PR_BODY set for a local lint.
- Waiting-page item for the "page made BEFORE a clean merge" carry: not raised; needs its own owner ruling (tests test_b_f_ and test_b_g_ pin it as not carried).

## Next step for whoever picks this up
1. Read each PR's live head and `merge --reviewed` (main tool). 2. On the coordinator's word that a PR is marked ready and its ready run is green by all-jobs-passed: read main's newest finished push run; merge with `merge <N> --confirm --head <sha>` in the order #3481, #3489 (retarget to main), #3519, #3491; report each with a REST read. 3. After #3481 and #3489 land, write the notes PR.

## Refused acts and tool refusals met
- Hand-made worktree guard refused a test-author's red checkout twice (guard text: "a worktree comes only from the Agent tool's isolation 'worktree' option or from the EnterWorktree tool"). Its red run used its own worktree at the base instead.
- `merge --review-record --fix-check` on #3519 refused (rc=2) because no earlier log named 92340bc786: verbatim "merge: --fix-check: the reviewed head must be the Head of the newest earlier review log on this pull request, and that log must have no Fix check line or a PASS one. After a PASS one, a head that is a merge must be a merge of the base into that Head, and the log must read done, with no edit beyond git's merge; a merge that conflicts may edit its conflicted paths only. A clean merge of main needs no fix verifier." Resolved by a fresh full sonnet round 1 (coordinator's pick b).
- GitHub REST rate limit hit once for the shared gh login (a print waited 21 min); reset 18:27:34Z Nov 15.
- No push or merge was refused. A `git worktree add` by hand was refused for a test-author.

## Owner rulings I hold (each has a home)
- Own-850-a (clean-merge carry only), lifted by owner pick a at 2026-11-15 11:39 CST on page item pick-carry-lint-after-claim (n 868): claim or page AFTER a clean merge carries; BEFORE does not. Home: decision sentences in `lanes-run-no-full-ci-job` and `pr-review-record`, in #3519.
- "Lanes can merge claude-settings PRs" (owner 11:12 CST Nov 15 via the consultant, relayed by the coordinator). Home: coordinator message 11:15 CST; marking ready stays runner 10's.
- Hand-in order (coordinator 12:07 CST Nov 15): merge main into the head, lint, then hand in.

## Agents (all finished; none running)
- test-author haiku: rct-lint-page-nostamp tests 4c7d74afe2; rct-lint-after-claim tests 54897ad82c; notes #3491 via record-writer 93819df8fd. (worktrees removed)
- builder sonnet: rct-lint-page-nostamp cef0f04675; rct-lint-after-claim 8b810f43e6 and docstring fix e8ea9c971e; rct-lint-comment 4872164bbc (#3481 docstring).
- record-writer haiku: rct-notes-review-carries 93819df8fd (#3491); rct-lint-after-claim-docs 92340bc786 (#3519 decision sentences).
- reviewers sonnet: #3481 rounds 2 and 3, fix check; #3489 round 1 (haiku); #3519 round 1 (two, the second fresh) and a fix check.
- Local branches and worktrees left on this cloud machine: rct-lint-comment (.claude/worktrees/agent-a2ca6fd8d9980fb84), rct-review-line54 (.claude/worktrees/rct-line54), rct-lint-after-claim-m (.claude/worktrees/rct-lint-combine). Not needed: every commit is on origin.

## Files and commands
- merge/merge.py `lint_carried`, `clean_merges_after(trailing_only)`, `claim_only`; merge/test_merge.py `LintCleanMainMergeCarry`, `LintPageCarryWithoutStampKinds`; docs/decisions/lanes-run-no-full-ci-job.md, docs/decisions/pr-review-record.md.
- Print a review log: `~/.claude/bin/verdict python3 <main source>/merge/merge.py N --review-record --head FULL40 --kind normal --guard yes --round 1:reviewer:sonnet:PASS --net-value "not owed"`; post with the GitHub MCP comment tool. Lane lint from the main clone, one at a time, in the background: `~/.claude/bin/verdict ~/.claude/bin/merge -C /home/user/claude-settings N --lane-lint`.
- Local session handoff (cloud machine, may not survive): /root/.claude/handoffs/8c70e9c7-82b9-52ec-b64a-59801ad7ab8d.md.
