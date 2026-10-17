# A bare merge in a merge-tool repo asks

## The ruling

Orchestrator call (lane bare-gh-merge-ask); the owner may rule otherwise. Guard rule id `bare-merge`, verdict ask. It runs after the merge-checks gate, so a deny still wins and the ask never turns a main refusal into an ask.

- The rule fires on a `gh pr merge` segment when the stamp config of the working tree holds a `merge` key.
- `uses_merge_tool` in `hooks/guard_merge.py` starts at the call's folder (a leading `cd` target, else the payload cwd). It walks up to the nearest folder that holds `.git` (folder or file) and reads `.github/stamp.json` there. A call from a subfolder reads the repo's stamp. It tries the cwd as written and with symlinks resolved.
- No `.git` above the folder allows. A missing, unreadable, invalid or non-object file allows, silently.
- Quoted text, heredoc bodies and comments that name a merge are text, as in merge-checks.
- The reason names `merge <pr> --confirm` (the merge tool) and does not echo the repo path.

Why ask and not deny: a broken merge tool leaves a bare merge as the only way to merge. A refusal would block the recovery on the day it is needed (`verification-recovery-not-gated-on-own-state`). An ask keeps the path open and still stops a bare merge made by habit. Why a rule at all: bare merges left the local main four commits behind origin.

## Holes, named

- The hook reads the stamp from the working tree, not from the base branch. A lane that edits `.github/stamp.json` changes the ask for its own session.
- A confirmed ask merges bare. That is the recovery path by design.
- A bare merge chained after a step that is not harmless (`ls && gh pr merge 12`) is denied as ask-alone, not asked. That is stricter than main. The remedy is to split the command and run the merge alone.
- Debts: `bare-merge-reads-folder-not-repo` (`gh pr merge -R other/repo` reads the stamp of the folder, not of the named repo). `bare-merge-skips-host-merge-tool` (`mcp__github__merge_pull_request` is judged by merge-checks and not asked). `bare-merge-tool-unloadable` (a merge tool that will not load returns unknown, and the deny comes before the ask, so the owner is never asked).

Kind: build
Plan: decisions/bare-merge-asks.md#the-ruling (all)
Home: hooks/guard_merge.py
