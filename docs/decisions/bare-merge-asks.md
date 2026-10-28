# A bare merge in a merge-tool repo asks

## The ruling

Orchestrator call (lane bare-gh-merge-ask); the owner may rule otherwise. Guard rule id `bare-merge`, verdict ask. It runs after the merge-checks guard, so a refusal still wins and the ask never turns a main refusal into an ask.

- The rule fires on a `gh pr merge` segment when the stamp config of the working tree holds a `merge` key.
- `uses_merge_tool` in `hooks/guard_merge.py` starts at the call's folder (a leading `cd` target, else the payload cwd). It walks up to the nearest folder that holds `.git` (folder or file) and reads `.github/stamp.json` there. A call from a subfolder reads the repo's stamp. It tries the cwd as written and with symlinks resolved.
- No `.git` above the folder allows. A missing, unreadable, invalid or non-object file allows, silently.
- Quoted text, heredoc bodies and comments that name a merge are text, as in merge-checks.
- The reason names `merge <pr> --confirm` (the merge tool) and does not echo the repo path.

Why ask and not refuse: a broken merge tool leaves a bare merge as the only way to merge. A refusal would stop the recovery on the day it is needed (`verification-recovery-independent-of-state`). An ask keeps the path open and still stops a bare merge made by habit. Why a rule at all: bare merges left the local main four commits behind origin.

Kind: build
Plan: docs/decisions/bare-merge-asks.md#the-ruling (all)
Home: hooks/guard_merge.py
