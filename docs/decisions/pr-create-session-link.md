# A pull request opened by MCP carries its session's link in the body

## The ruling

Question: may a session open a pull request by the GitHub MCP create tool with a body that holds no `Session: https://claude.ai/code/<id>` line for its own session? Ruling: no. Guard rule `pr-create-session-link` refuses the call and gives the line to add (roadmap step `pr-create-session-link`).

- The merge tool refuses `--confirm` for a body with no link to the merging session (`own_session_link` in `merge/merge.py`). The guard asks that same reader, and builds the line from the session id `remote_session_id` in `hooks/override.py` reads, so no copy of the link pattern sits in the guard.
- The refusal gives the exact line to add. It names no tool or flag it refuses (rule `git-remedy-never-names-target`).
- Judged in a repo that uses the merge tool. A call with the link, a local session (no session id in the env), an unloadable merge tool and another tool pass. A body that is missing or not a string reads as a body with no link.
- Scope: the MCP create tool only. A session id is known only in a cloud session, where a `gh pr create` is already refused (rule `gh-write-cloud`). A local `gh pr create` has no id to check.
- An override lifts it (decision `owner-override`).

## Incident, risk and cost

Mistake: an agent opens a pull request by MCP and leaves the link out. Harm: the merge tool refuses the confirm late, after review and CI, and the session must edit the body then. The check moves that refusal to creation, where the fix costs one retry. Risk kind: named incident, count not measured.

Cost: one env read per create call. In a cloud session in a merge-tool repo it also loads the merge tool once. No file is written, no process outlives the call.

Kind: build
Plan: docs/decisions/pr-create-session-link.md#the-ruling (all)
Home: hooks/guard_merge.py
