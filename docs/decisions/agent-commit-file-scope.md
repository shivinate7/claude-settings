# An agent's commit touches only the files its brief names

## The ruling

A builder, test-author or record-writer may modify or delete an existing file only if its brief names it. The guard reads the brief at commit, push and SubagentStop and refuses the rest (rule `brief-scope-diff`). The refusal names no path. It says: restore the file; if a commit of yours holds the change, stop and report it; if the task needs it, report it to the orchestrator. The middle step is `OWN_COMMIT_REMEDY`, the one home `builder_diff_reason` also reads.

Basis, coordinator, 2026-11-08 16:08 CST. Two incidents. A record-writer's brief named notes by the prefix `verdict-`. Its commit changed 12 notes of another tool (PR 2041, 14:51 CST). A test-author's commit rewrote `lint/test_retired_repos.py`, which its brief did not name. Harm: a commit silently rewrites files outside its task, and only a hand diff catches it. The step `notes-scope-own-lines` covers notes lines only.

- **The brief.** The first user message of the agent's own transcript, `<dir of transcript_path>/<stem>/subagents/agent-<agent_id>.jsonl` (`stall_watch.agent_transcripts` builds the path). At SubagentStop the payload's `agent_transcript_path` is read first. A later message adds nothing. Another agent's transcript is never read.
- **A pointer** (owner rulings, coordinator, 2026-11-08). A path in the message whose file name holds `brief` and ends `.md` or `.txt` points at a brief file. Each pointer is read if its file is a plain file of at most 64 KB in the checkout or under the temp folder (a session's scratchpad is there). The names in each file read are added to the message's own names; only the pointer itself names nothing. A file read is not searched for a pointer. If any pointer cannot be read, the commit logs `brief-scope-unread` and is allowed, whatever else the message names.
- **A named path.** A run of the brief's path characters that is one of: a path with a `/`; a bare file name (it ends in an extension); a folder ending in `/`; a glob; or a backticked name prefix ending in `-`, such as `verdict-`. A prefix counts only when backticked (owner's pick). A run with a `/` counts only in one of three cases. It ends in an extension. It ends in `/`. Or its first segment is a folder at the top of the agent's checkout. So prose slash words (`and/or`, `I/O`, `pass/fail`, `Round 2/3`) name nothing. A run keeps `[ ] ( ) + $`, so `app/[id]/page.tsx` and `routes/posts.$id.tsx` are one path each. A bracket or paren the run does not close, and a markdown link's `](`, end a name. An apostrophe or a colon ends a run, so a lone apostrophe breaks no read.
- **In scope.** Five kinds of path. A path equal to a named path. A path under a named folder, whole segments only (a folder written with no trailing slash counts, `docs/decisions`). A path matched by a named glob. A file whose name equals a named bare name. A file whose name starts with a named prefix. A run of stars in a glob is one star, and the match does not backtrack, so ten stars are judged at once. Also the pages a tool writes, whatever the brief says. They are the catalog and the records index (`lint/hook_catalog.py`, `PAGE` and `RECORDS_PAGE`), and the map folder (the `map` kind of `lint/layout.json`). `generated_pages` reads those constants.
- **New or existing.** Judged at the agent's base: the merge base of HEAD and the default branch (`origin/main`). A file the base does not hold is new, so a file an own earlier commit added stays new. Without a readable base, the parent of the change judged is used.
- **Refused.** A modified or deleted existing file outside scope, at commit, push and the first stop. The refusal is final: no override lifts it, as for `builder-diff`. A builder's test path is judged first (`builder-diff`). A second stop logs `brief-scope-unresolved` and allows, so an agent that cannot fix its tree never loops.
- **Logged and allowed.** A new file outside scope (`brief-scope-new`). A brief that names no path (`brief-scope-unnamed`). A brief, transcript path, pointer or page list that cannot be read (`brief-scope-unread`).
- **Not judged.** The main session, a reviewer, an Explore, a designer, and an agent with no `agent_id`.
- **Absolute paths.** One inside the agent's checkout counts as its repo path. So does one inside the primary checkout, when the agent's checkout sits under its `.claude/worktrees`. One outside both names no path.

Limits.
- Names match case-folded: `Src/App.py` names `src/app.py`. This fails open.
- The `stall_watch` import that finds the agent's transcript runs at every commit and push of an agent with a role. The transcript is read at each of those whose agent has a change of its own.
- A Windows path written `C:\...` names no path.
- An absolute path behind a symlink that the checkout's root does not share names no path.
- A bare file name (`app.py`) and a glob with no `/` match a file of that name at any depth.
- A path the brief mentions to forbid it counts as named: "(read only)" and "do not touch `x.py`" name `x.py`.
- A pointer file's own name names nothing. A brief that says "update `skills/project-ops/templates/brief.md`" has that file refused, because its name holds `brief` and ends `.md`. Name its folder or a glob instead.
- `e.g.` and `i.e.` read as bare names (`e.g`, `i.e`). A brief with no real path but one of them counts as naming, so a changed existing file is refused, not logged `brief-scope-unnamed`.
- A long unbroken run after a backtick is quadratic: 20,000 characters take about 1 s, 70,000 take 10.5 s.
- A replay the agent made (a `git revert`, a hand-resolved cherry-pick, a rebase squash) is logged under the role's own rule and never judged here, as for `builder-diff`.
- Unstaged edits to a file outside scope are judged with the commit: the working tree is part of the agent's own change, whether or not `git add` named it.
- A pointer is followed one level.

## Cost

One `stall_watch` import at each commit and push of an agent with a role. One read of the agent's transcript at a commit, push or stop. It happens only when the agent has a change of its own to judge, and it stops at the first user record. Each pointer adds one read of one file of at most 64 KB. A run with a `/` and no extension adds one listing of the checkout's top folder, once per judgement. The first path outside scope adds an import of `lint/hook_catalog.py`, a default-branch read and one `git merge-base`. Each such path adds one `git cat-file -e`. No timer, no process, no file written except the one guard.log line a refusal or a logged state writes.

The reader of those lines is `lint/guard_log_report.py` (rules `brief-scope-diff`, `brief-scope-new`, `brief-scope-unnamed`, `brief-scope-unread`, `brief-scope-unresolved`). A cull reads `brief-scope-unread` and `brief-scope-unnamed` to see how many briefs the guard could not judge.

## Measure

`GUARD_FAMILY=brief-scope python3 hooks/test_guard.py`: 65 of 65 cases pass on this tip.

Kind: build
Plan: docs/decisions/agent-commit-file-scope.md#the-ruling (all)
Home: hooks/guard.py
