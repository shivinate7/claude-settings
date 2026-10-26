# c70: a refusal with one lossless fix hands the session that fix, so it never asks shiv

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 54f2dfd.
Base: main 54f2dfd; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Finding (shiv's gripe, Oct 26)

When the branch guard refuses a delete because the branch holds the only copy of its commits,
sessions stop and ask shiv "push as an archive, then delete?". That is always the right move.
hooks/guard_branch_worktree.py BRANCH_DELETE_DENY_REASON ends "Remedy: push the branch, or merge
it, before it is deleted": a choice, no command.

## Task

1. Red first: show the current message leaves the session a choice (quote it in the test).
2. The branch-delete refusal names the exact next step: push the branch to an archive ref on
   origin, then delete it locally. Pick one archive ref shape (for example `archive/<branch>`) and
   say why. The message never names the refused target (rule git-remedy-never-names-target): it
   uses a placeholder the session fills. A test pins the new message and that the remedy, once
   run, makes the guard allow the delete.
3. One CLAUDE.md line, anchored, beside the shared-trees or git rules: an archive push of an
   unmerged branch, then the local delete, is pre-approved and needs no question, since nothing is
   lost. Keep it to one sentence.
4. Sweep every guard refusal (hooks/guard*.py): where one safe, lossless fix exists, the message
   hands it over as a command shape. List every refusal in the PR body as "fix handed" or "no
   single lossless fix, why".

## Fences

- Change messages and the one CLAUDE.md line only. No refusal becomes an allow, and no allow
  becomes a refusal: verdicts stay exactly as on main (prove it with the guard suite).
- #615 (o2, one layout for every repo) changes the record-cite part of hooks/guard.py; keep clear
  of record_folders and record_path_pattern.

## Failure classes and proof

- Run the guard suite and gates-mutate-guard's harness (python3 hooks/mutate_guard.py) through
  `verdict`. A mutant anchored on a message you change must be re-pointed, not deleted.
- Touches a rule and the guard's messages: review rounds per roles-review-cap-three, fresh
  Sonnet reviewer from round 1.

## Report

Cap 20 lines: Done, Deviations, Next, and the refusal sweep count (handed / not). Send the green,
reviewed head and branch to "Advise the claude-settings build (3)". Do not merge, and do not
rebase onto main. No question for shiv: park any in the PR body.
