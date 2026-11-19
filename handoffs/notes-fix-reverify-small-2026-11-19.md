# Handoff: notes-fix-reverify-small

Written 2026-11-19 00:29 CST.

Status: code PR 3039 is open as a draft and its CI is not read. The prose PR is not opened.

## Lane

- Slug: notes-fix-reverify-small. Roadmap step: notes-fix-reverify-small.
- Task: fix the small rows and the prose Fix notes from the kept-notes re-check.
- The rows came from reverify-fix.tsv and reverify-prose-fix.tsv on branch claude/notes-keep-reverify.
- Lane session: session_013NEJKzkcpx9EGjr8ctAJbs.
- Parent coordinator session: session_013NEJL1gw6EdrSyvHkTUEx6.
- Batch runner 10 session: session_013NEJL2f1YCYsvLdpFqtWP3.
- Triage session: session_013NEJKzCzoWhfP8FMCPtQU6.

## Open PRs

- PR 3039 is the code PR. It is a draft. Its base is main.
- Head: branch notes-fix-reverify-small-code, tip 1ee95ce1d.
- It holds 13 small code rows.
- Batch runner 10 got it on 2026-11-12 at 18:52 CST.
- This lane did not read its CI result.
- It overlaps PR 3034 (branch cull-shared-tree). Both use the same relative -C reader. One of them needs a rebase.

## Branches on origin

All branches below are pushed. Only PR 3039 has a PR. Each tip is the branch's last commit.

- notes-fix-small-guard, tip 0cc7c1910. Rows in hooks/guard.py.
- notes-fix-small-other, tip 536b1c6f0. Silent-undo ./ strip. Literal and backslash home delete. perl and ruby -i, including -0pi.
- notes-fix-small-core, tip 703d8ce72. Per-segment folder, owner item 621 option A. Heredoc indented closer. gtimeout and watch wrappers.
- notes-fix-reverify-small-code, tip 1ee95ce1d. Integrates the three branches above. Adds the wrapped-script fix f04b6dfad and pins 1ee95ce1d.
- notes-fix-reverify-prose, tip 20d436884. Rewrites 3 of 13 prose rows in docs/debts/notes.md. Its base is an older main. It is not rebased on PR 2743, which edits the same file and has not landed.
- notes-small-review-findings, tip 1bbe023d7. Adds 9 notes lines of open review findings. It edits docs/debts/notes.md only.

## Done

- 13 code rows built. Each row was tested red, then green.
- Code reviews:
  - notes-fix-small-guard: round 1 FAIL. Fix verifier PASS.
  - notes-fix-small-other: round 1 FAIL. Round 2 PASS. Fix verifier PASS.
  - notes-fix-small-core: rounds 1 and 2 FAIL. Round 3 PASS with positive net safety value.
  - notes-fix-reverify-small-code (integration): round 2 FAIL on two untested paths. Fix verifier PASS. Net safety value positive.
- Prose: 3 rows rewritten in docs/debts/notes.md: merge-superseded-cancel-only, designer-unpushed-worktree-lost, base-pin-interrupt-skips-ff.
- Prose: 10 rows skipped.
  - 6 slugs are missing from main's notes.md: mutant-load-unproven, merge-retarget-before-merge, task-names-check-line-not-truth, ios-probe-subshell-arg-drops-action, guard-log-kolkata-needs-tzdata, silent-undo-fetch-untested.
  - 4 already had the Fix, or were duplicate lines that PR 2743 removes.

## Unfinished

1. The prose PR is not opened.
   - Rebase notes-fix-reverify-prose and notes-small-review-findings on PR 2743 once it lands.
   - Then open one draft PR for the prose. Prose batches alone (owner's waiting page, item 521).
   - The 6 missing slugs need an answer from the owner or triage: retired or renamed.
2. PR 3039 CI is not read. The full suite and the mutation test run only in CI.
3. Row env-node-env-file-prints is stale. node --env-file with -e/-p/--eval/--print already denies on main.
   - Optional follow-up: green-on-main pins for the spaced -p, --eval and --print forms.
4. Review limits, filed as notes and not fixed:
   - An inner cd inside a wrapper script is not walked.
   - env -C before a wrapper is ignored.
   - A wrapper in $() takes the whole-call folder.
   - A git segment in $() or backticks after another cd takes the whole-call folder.
   - The docstring of _read_git_segments lists three readers. A fourth was added (nit).

## Next step

Batch runner 10 reads CI on PR 3039 and merges it under its rules. Then open the prose PR as above.

## Refused acts

- The hand-made-worktree guard refused a worktree made by hand. An agent worktree was used instead.
- The brief-claim-has-probe guard and the brief-destructive-git guard refused two briefs. Both were reworded.
- No push or merge was refused.

## Owner rulings held

- Owner item 621, option A, 2026-11-12 14:13 CST: each command is judged by the folder it names. The answer file answers/git-c-per-segment is kept by triage.
- Triage ruling, 2026-11-12 13:52 CST: env-file narrowing needs no waiting-page item. None built. The row is stale.

## Agents

All agents below finished. None is running.

- Record-writer notes-fix-reverify-prose (haiku).
- Test-authors (haiku) on notes-fix-small-guard, notes-fix-small-core, notes-fix-small-other and notes-fix-reverify-small-code.
- Builders (sonnet) on the same branches. Two builders ran on opus: one for the -0pi flag on notes-fix-small-other, one for the ln folder fix on notes-fix-small-core.
- Reviewers: haiku in round 1, sonnet from round 2. On the guard, core, other and integration branches.
- Record-writer notes-small-review-findings (haiku).
