# A bare merge in a merge-tool repo is denied

## The ruling

Orchestrator call (lane bare-gh-merge-ask), changed by the owner's sort of 2026-11-23 11:07 CST (decision `guards-never-ask`). Guard rule id `bare-merge`, verdict deny. It runs after the merge-checks guard, so a merge-checks refusal still wins.

- The rule fires on a `gh pr merge` segment when the stamp config of the working tree holds a `merge` key.
- `uses_merge_tool` in `hooks/guard_merge.py` starts at the call's folder (a leading `cd` target, else the payload cwd). It walks up to the nearest folder that holds `.git` (folder or file) and reads `.github/stamp.json` there. A call from a subfolder reads the repo's stamp. It tries the cwd as written and with symlinks resolved.
- No `.git` above the folder allows. A missing, unreadable, invalid or non-object file allows, silently.
- Quoted text, heredoc bodies and comments that name a merge are text, as in merge-checks.
- The reason names `merge <pr> --confirm` (the merge tool), does not echo the repo path, and ends with the comply-anyway line.

Why deny, not ask: every ask ends (owner, 2026-11-23 10:49 CST). The old ask kept a bare merge open for a broken merge tool. The deny closes that path. When the merge tool is broken, the owner's typed `override` lifts this refusal for that one act (decision `owner-override`), and that route does not depend on the merge tool. Why a rule at all: bare merges left the local main four commits behind origin.

Kind: build
Plan: docs/decisions/bare-merge-asks.md#the-ruling (all)
Home: hooks/guard_merge.py
