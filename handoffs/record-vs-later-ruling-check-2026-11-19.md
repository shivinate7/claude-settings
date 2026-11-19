# Handoff: lane record-vs-later-ruling-check, 2026-11-19

Lane slug: record-vs-later-ruling-check. This lane: session_013NEJKzCLNUNqCwEF8se48h. Parent (coordinator): session_013NEJL1gw6EdrSyvHkTUEx6. Repo: shivinate7/claude-settings.

## What it is
Grant own-mechanical-before-cleanup (owner, 11:07 CST Nov 15): a mechanical check that a Markdown file does not cite an older owner ruling and miss the later ruling that overtakes it. Incident: decision all-repos-switch-together kept "mailaudit merges in a batch until the cutover" after ruling own-820-c-five-repos overtook it.

## Branches and PRs (REST read 2026-11-19 00:25 CST)
- PR 3559, draft, open, not merged. Branch ruling-overtakes-record-2, head 8b872183d4018acadb05f19d7f39b3d18d9c933a, base main 685fa1631cb5. Two commits (7a1d6874, 8b872183), each with a Red-run trailer. Four files: lint/ruled_store.py, lint/test_ruled_store.py, actions/claude-md-cites/action.yml, docs/decisions/ruled-store-one-home.md.
  - Review record comment 6901803021 (Round 1 reviewer sonnet PASS, guard yes, net value not owed).
  - Lane lint PASS at that head with PR_BODY. A lane-lint comment 6902220971 was reported by the coordinator.
  - lane-touched-tests run 43764194268: success. Full test_ci_job 239 OK on the head.
  - Fix verifiers (sonnet) PASS: 213d8ed8..7a1d6874 and 213d8ed8..8b872183.
  - Handed to runner 10 on 2026-11-15 16:14 CST. Runner 10 marks and merges. This lane never merges it. It was still a draft, unmerged, when this file was written.
- PR 3507, closed as replaced. Branch ruling-overtakes-record, head 62f4b9ae. Superseded by 3559. Review comments 6900395639 (Round 1 on 9303fbae) and 6900398956 (record at 213d8ed8).
- This file's branch: archive/handoff-record-vs-later-ruling-check.

## Done
check_records / subcommand `ruled_store.py records REPO [--changed BASE] [--report] [--fetch]`: a tracked .md file that cites an older ruling's id and not the later ruling that overtakes it is flagged with file and line. Step 3 of actions/claude-md-cites, pull requests only, touched files only. Overtaking is read from a `ruling`-kind supersedes ref first, then one prose sentence with an overtaking verb (fallback). Comment openers in code spans and fences are read as text; a non-UTF-8 file prints unknown. 71 ruled-store cases; 12 red on main's module. Real findings on main at 2026-11-15: 3 (all-repos-switch-together.md:7, draft-until-reviewed.md:11, skills/ci-hygiene/SKILL.md:59), all fixed by PR 3504.

## Unfinished
1. Merge of PR 3559: runner 10's.
2. Round 1 low findings with no tracked home yet (a push was forbidden while the PR was in runner 10's hands):
   - the prose fallback ignores an explicit supersedes_none (own-lane-lint-allow-b pairs with own-839-a-review-record-allow-entry); second false pair after own-766-b-field-now; no tracked file cites either older id;
   - docs/decisions/brief-ids-in-roster.md:8 is an arguable flag on the fresh store (findings on main: 4, three real, one arguable);
   - the --fetch sentence in the decision record names the wrong cause for main never going red ("pull requests only" is the cause); the module Cost note still says it writes no file;
   - no test of a --fetch that succeeds.
   Home: a note in the repo's notes folder, or a debt; the lane supersedes-names-an-id replaces the prose fallback.
3. Not covered by this check (told to the coordinator): State-line claims against live facts; files naming neither ruling id.

## Next step
When PR 3559 merges: file the four findings in the notes folder (docs lane), and read the merge for the report's pace numbers.

## Refused acts and corrections
- The lane lint first refused with: "the draft run of lane-touched-tests on 8b872183d is not finished, not a pass" (run queued 10+ min). I did not use --lint-unknown-ok. It passed on the re-run.
- Correction sent to the coordinator: the CodeCheckFromCopiedInstall error was NOT main's; it passes on a real clone of main. A git archive copy has no .git.
- The tool printed a chained Fix check record only after an earlier log at the reviewed head; on 3559 I posted a plain Round 1 record after a real Round 1 instead of claiming a round at a head no reviewer read.

## Owner rulings this lane holds
- own-mechanical-before-cleanup (owner 11:07 CST Nov 15, grant): build this check.
- Item 877 (owner 11:33 CST Nov 15): option a, require the overtaken ruling's id in `supersedes`. Built by lane supersedes-names-an-id, not here.
- Owner 11:12 CST Nov 15, via the coordinator: lanes merge claude-settings PRs. Then the coordinator said runner 10 merges 3559 and this lane does not.
- The cloud scope ruling (owner 11:10 CST Nov 15): one check, inside actions/claude-md-cites, no per-repo checks.

## Agents (all finished; none running)
- reviewer sonnet, round 1 on 35afc0b3/9303fbae: id a2afdb4a7c4137c9c, worktree branch worktree-agent-a2afdb4a7c4137c9c.
- reviewer sonnet, fix check 9303fbae..213d8ed8: id ad358b9331c31203f.
- reviewer sonnet, fix check 213d8ed8..7a1d6874: id a1758d1fe640eeeef.
- reviewer sonnet, fix check 213d8ed8..8b872183: id af81eac35fc18c08c.
- reviewer sonnet, round 1 on 3559: id a25eff8205c011f3e.
