# Handoff: lane aligned-agents-skills-scope, 2026-11-19

**Slug.** `aligned-agents-skills-scope` (lane once called `aligned-check-agents-skills`).
**Branch.** `aligned-agents-skills-scope`, head `85d008554`. Old branch archived at `archive/aligned-cover-agents-skills` (head `4a1acdc18`, same tree).
**Open PR.** #3526, draft, head `85d008554`. Main at last read: `4022a76b2`. Last base merged in: `ae13fcab`, because #3507 had not landed.

## Done
- `aligned` (lint/compliance_probes.py `rule_scope(root, agents_skills=True)`) reads Markdown under top-level `agents/` and `skills/`. `restates` keeps its old scope.
- In those folders a sentence also ends at `.`, `!` or `?` and a space outside a code span. An unclosed fence hides the rest of its file and does not make the group unknown.
- Remedy text and docs now say: re-read each citing sentence against this change and clean what rotted. The `Rules checked:` line is unchanged (owner item 873 a, his note on cleaning rot deeply).
- Measure on main (123 merges, shallow clone, empty PR body): 84 sentences in 90 files cite a record. Old scope flagged 57 merges, new 79, so n = 22 newly flagged.
- Review: round 1 FAIL (reviewer haiku), round 2 FAIL tests only (reviewer sonnet), fix check PASS (reviewer sonnet). `merge --lane-lint` PASS at `85d008554`.
- Debt `aligned-skips-agents-skills` narrowed to `output-styles/`. Two notes lines added for residual limits.

## Unfinished
- #3507 was replaced by #3559 (same action file). It had not merged when I last heard.
- Merge main into the branch (plain merge, no rebase, no force), put the review record at the live head, re-run `merge --lane-lint aligned-agents-skills-scope`, send the coordinator the head, the record comment id and the lint comment id.
- `docs/records.md` row for the debt is stale. The merge rebuilds it; a lane never commits it.

## Next step
When #3559 merges: merge main, lint, hand in. Batch runner marks #3526 ready.

## Refused acts
- Memory `ls` relayed by the coordinator at 12:11 CST on 2026-11-15: not run.
- The first handoff order (00:23 CST, 2026-11-19) came with no owner confirmation, so I held it; the coordinator's second message confirmed it.
- Hook refusals met and obeyed: records page not committed by a lane; Red-run trailer needed a new branch for a pushed commit.

## Owner rulings held
- Waiting-page item 872, option b: add `agents/` and `skills/` Markdown to the aligned check (home: decision `child-cites-not-copies`).
- Item 873, option a: keep the required `Rules checked:` line as built. His note: the line must not let a session cite a rule only to defer to it; the point is to check the rules against the change so the rot is cleaned deeply (home: same decision, line on the remedy).
- `output-styles/` is unruled; owner pick still open.

## Agents
- test-author haiku, id a075b3e938323ee43, worktree branch `worktree-agent-a075b3e938323ee43`. Finished.
- reviewer round 1 haiku (abb9a2b0d427cda2e), round 2 sonnet (a6cb9357fe7753e65), fix check sonnet (a4b0edaad2d75a2ef). All finished; none running.
