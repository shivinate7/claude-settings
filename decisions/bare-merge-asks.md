# A bare merge in a merge-tool repo asks

## The question

How does the guard stop a bare `gh pr merge` from skipping the merge tool in a repo that uses it?

## The ruling

Orchestrator call, lane bare-gh-merge-ask. It replaces the deferred item on the same question.
Rule id `bare-merge`, verdict ask. It runs after the merge-checks gate, so a deny still wins and
the ask never turns a main refusal into an ask.

The rule fires on a `gh pr merge` segment when the stamp config of the working tree holds a
`merge` key. `uses_merge_tool` in hooks/guard_merge.py starts at the call's folder (a leading `cd`
target when there is one, else the payload cwd), walks up to the nearest folder that holds `.git`
(a folder or a file), and reads `.github/stamp.json` there. A call from a subfolder reads the
repo's stamp. No `.git` above the folder allows. The file must parse
as a JSON object. A missing, unreadable, invalid or non-object file allows, silently. Quoted
text, heredoc bodies and comments that name a merge are text, as in merge-checks.

The reason names `merge <pr> --confirm` (the merge tool) and does not echo the repo path.

Incident: claude-sharables, 2026-10-06. Four merges by plain `gh pr merge` left the local main four
commits behind origin. A later session read a stale file and nearly bumped a version wrong.

Kind: build
Plan: decisions/bare-merge-asks.md#the-ruling (all)
Home: hooks/guard_merge.py

## Why ask and not deny

A broken merge tool leaves a bare merge as the only way to merge. A refusal would block the
recovery on the day it is needed (`verification-recovery-not-gated-on-own-state`, a recovery
control must not depend on the state it recovers). The deferred item waited for this reason. An
ask keeps the path open and still stops a bare merge made by habit. Orchestrator call; the owner
may rule otherwise. The owner can answer the ask yes only when the head read is green; see the
hole on a merge tool that will not load.

## The trigger check

The deferred item came back when two things held on main. Both hold. `install.sh` puts
`~/.claude/bin` on PATH (lines 584-586), and the coordinator counted six other `stamp.json`
files with a `merge` block, 2026-10-17 (not re-measured in this lane).

## Holes, named

- The hook reads the stamp from the working tree, not from the base branch, as the merge tool
  does. A lane that edits `.github/stamp.json` changes the ask for its own session.
- `gh pr merge -R other/repo` reads the stamp of the folder, not of the named repo. Debt
  `bare-merge-reads-folder-not-repo`.
- The host tool `mcp__github__merge_pull_request` is judged by merge-checks and not asked by
  this rule. Debt `bare-merge-skips-host-merge-tool`.
- A confirmed ask merges bare. That is the recovery path by design.
- A merge tool that will not load is not recoverable by a bare merge. `merge_gate` returns
  unknown, and the merge-checks deny comes before the ask, so the owner is never asked. The
  recovery the ask exists for then needs the owner to merge outside the hook. Debt
  `bare-merge-tool-unloadable`.
- A bare merge chained after a step that is not harmless (`ls && gh pr merge 12`) is denied as
  ask-alone, not asked. That is stricter than main, which allows the chain. The remedy is to
  split the command and run the merge alone.
