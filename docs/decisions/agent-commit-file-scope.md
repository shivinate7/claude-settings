# An agent's commit touches only the files its brief names

## The ruling

A builder, test-author or record-writer may modify or delete an existing file only if its brief names it. The guard reads the brief at commit, push and SubagentStop and refuses the rest (rule `brief-scope-diff`). The refusal names no path. It says: restore the file, and if the task needs it, report it to the orchestrator.

Basis, coordinator, 2026-11-08 16:08 CST. Two incidents: a record-writer's brief named notes by the prefix `verdict-`, and its commit changed 12 notes of another tool (PR 2041, 14:51 CST); a test-author's commit rewrote `lint/test_retired_repos.py`, which its brief did not name. Harm: a commit silently rewrites files outside its task, and only a hand diff catches it. The step `notes-scope-own-lines` covers notes lines only.

- **The brief.** The first user message of the agent's own transcript, `<dir of transcript_path>/<stem>/subagents/agent-<agent_id>.jsonl` (`stall_watch.agent_transcripts` builds the path). At SubagentStop the payload's `agent_transcript_path` is read first. A later message adds nothing. Another agent's transcript is never read.
- **A named path.** A run of the brief's path characters that is one of: a path with a `/`; a bare file name (it ends in an extension); a folder ending in `/`; a glob; or a backticked name prefix ending in `-`, such as `verdict-`. A prefix counts only when backticked (owner's pick). An apostrophe, a colon or a bracket ends a run, so a lone apostrophe breaks no read.
- **In scope.** A path equal to a named path; under a named folder, whole segments only; matched by a named glob; a file whose name equals a named bare name; or a file whose name starts with a named prefix. Also the pages a tool writes, whatever the brief says: the catalog and the records index (`lint/hook_catalog.py`, `PAGE` and `RECORDS_PAGE`) and the map folder (the `map` kind of `lint/layout.json`). `generated_pages` reads those constants.
- **Refused.** A modified or deleted existing file outside scope, at commit, push and the first stop. The refusal is final: no override lifts it, as for `builder-diff`. A builder's test path is judged first (`builder-diff`). A second stop logs `brief-scope-unresolved` and allows, so an agent that cannot fix its tree never loops.
- **Logged and allowed.** A new file outside scope (`brief-scope-new`). A brief that names no path (`brief-scope-unnamed`). A brief, transcript path or page list that cannot be read (`brief-scope-unread`).
- **Not judged.** The main session, a reviewer, an Explore, a designer, and an agent with no `agent_id`.
- **Absolute paths.** One inside the checkout counts as its repo path. One outside it names no path, so a brief that only points at a file in a scratchpad reads as unnamed and allows.

Limits. A path the brief mentions to forbid it counts as named. A brief that points at another file for its task names only what it says itself. A glob with no `/` matches a file name at any depth.

## Cost

One read of the agent's transcript at a commit, push or stop, only when the agent has a change of its own to judge, and it stops at the first user record. One `git cat-file -e` per path outside scope, and an import of `lint/hook_catalog.py` on the first such path. No timer, no process, no file written except the one guard.log line a refusal or a logged state writes.

## Measure

`GUARD_FAMILY=brief-scope python3 hooks/test_guard.py`: 39 of 39 cases pass on this tip.

Kind: build
Plan: docs/decisions/agent-commit-file-scope.md#the-ruling (all)
Home: hooks/guard.py
