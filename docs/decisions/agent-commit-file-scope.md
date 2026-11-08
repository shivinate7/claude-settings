# An agent's commit touches only the files its brief names

## The ruling

A builder, test-author or record-writer may modify or delete an existing file only if its brief names it. The guard reads the brief at commit, push and SubagentStop and refuses the rest (rule `brief-scope-diff`). The refusal names no path. It says: restore the file, and if the task needs it, report it to the orchestrator.

Basis, coordinator, 2026-11-08 16:08 CST. Two incidents: a record-writer's brief named notes by the prefix `verdict-`, and its commit changed 12 notes of another tool (PR 2041, 14:51 CST); a test-author's commit rewrote `lint/test_retired_repos.py`, which its brief did not name. Harm: a commit silently rewrites files outside its task, and only a hand diff catches it. The step `notes-scope-own-lines` covers notes lines only.

- **The brief.** The first user message of the agent's own transcript, `<dir of transcript_path>/<stem>/subagents/agent-<agent_id>.jsonl` (`stall_watch.agent_transcripts` builds the path). At SubagentStop the payload's `agent_transcript_path` is read first. A later message adds nothing. Another agent's transcript is never read.
- **A pointer brief** (owner ruling, coordinator, 2026-11-08). A message that names a path whose file name holds `brief` and ends `.md` or `.txt` points at the brief. If the file exists, is a plain file of at most 64 KB, and sits in the checkout or under the temp folder (a session's scratchpad is there), its text is the brief, and the pointer path names nothing. It is read once: a pointer inside it is not followed. A pointer that cannot be read logs `brief-scope-unread` when the message names no other path; otherwise the message's own names stand.
- **A named path.** A run of the brief's path characters that is one of: a path with a `/`; a bare file name (it ends in an extension); a folder ending in `/`; a glob; or a backticked name prefix ending in `-`, such as `verdict-`. A prefix counts only when backticked (owner's pick). A run keeps `[ ] ( ) +`, so `app/[id]/page.tsx` is one path; a bracket or paren the run does not close, and a markdown link's `](`, end a name. An apostrophe or a colon ends a run, so a lone apostrophe breaks no read.
- **In scope.** A path equal to a named path; under a named folder, whole segments only (a folder written with no trailing slash counts, `docs/decisions`); matched by a named glob (a run of stars is one star, and the match does not backtrack, so ten stars are judged at once); a file whose name equals a named bare name; or a file whose name starts with a named prefix. Also the pages a tool writes, whatever the brief says: the catalog and the records index (`lint/hook_catalog.py`, `PAGE` and `RECORDS_PAGE`) and the map folder (the `map` kind of `lint/layout.json`). `generated_pages` reads those constants.
- **New or existing.** Judged at the agent's base: the merge base of HEAD and the default branch (`origin/main`). A file the base does not hold is new, so a file an own earlier commit added stays new. Without a readable base, the parent of the change judged is used.
- **Refused.** A modified or deleted existing file outside scope, at commit, push and the first stop. The refusal is final: no override lifts it, as for `builder-diff`. A builder's test path is judged first (`builder-diff`). A second stop logs `brief-scope-unresolved` and allows, so an agent that cannot fix its tree never loops.
- **Logged and allowed.** A new file outside scope (`brief-scope-new`). A brief that names no path (`brief-scope-unnamed`). A brief, transcript path or page list that cannot be read (`brief-scope-unread`).
- **Not judged.** The main session, a reviewer, an Explore, a designer, and an agent with no `agent_id`.
- **Absolute paths.** One inside the checkout counts as its repo path. One outside it names no path.

Limits.
- A bare file name (`app.py`) and a glob with no `/` match a file of that name at any depth.
- A path the brief mentions to forbid it counts as named: "(read only)" and "don't touch `x.py`" name `x.py`.
- A replay the agent made (a `git revert`, a hand-resolved cherry-pick, a rebase squash) is logged under the role's own rule and never judged here, as for `builder-diff`.
- Unstaged edits to a file outside scope are judged with the commit: the working tree is part of the agent's own change, whether or not `git add` named it.
- A pointer is followed one level.

## Cost

One read of the agent's transcript at a commit, push or stop, only when the agent has a change of its own to judge, and it stops at the first user record. A pointer adds one read of one file of at most 64 KB. The first path outside scope adds an import of `lint/hook_catalog.py`, a default-branch read and one `git merge-base`, and each such path one `git cat-file -e`. No timer, no process, no file written except the one guard.log line a refusal or a logged state writes.

The reader of those lines is `lint/guard_log_report.py` (rules `brief-scope-diff`, `brief-scope-new`, `brief-scope-unnamed`, `brief-scope-unread`, `brief-scope-unresolved`). A cull reads `brief-scope-unread` and `brief-scope-unnamed` to see how many briefs the guard could not judge.

## Measure

`GUARD_FAMILY=brief-scope python3 hooks/test_guard.py`: 55 of 55 cases pass on this tip.

Kind: build
Plan: docs/decisions/agent-commit-file-scope.md#the-ruling (all)
Home: hooks/guard.py
