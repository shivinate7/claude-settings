# A commit asks when it leaves a tracked edit behind beside a staged change

## The ruling

Coordinator, 2026-11-07 17:31 CST, to lane resumed-agent-stale-tree: warn, not refuse. A lone commit asks; in a chain, rule `ask-alone` refuses (last bullet below). Orchestrator's call, not an owner grant: the form and the read.

The guard rule `commit-leaves-edit-unstaged` asks before a `git commit` when a tracked file is modified in the work tree but left out of the commit. It asks only if a file in the same folder is in the commit.

- Only a plain `git commit` with no `-a`, no `--only`, `-o`, `-i` and no named paths is read. Those forms choose their files on purpose.
- In the commit: each path that differs between the index and HEAD. Left out: each tracked path whose work-tree copy differs from the index. Untracked files do not count.
- Same folder: the two paths share their parent folder. An edit left out in another folder passes.
- `--amend` and `--dry-run` are read the same way and pass the same way.
- One `git diff --cached --name-only` and one `git diff --name-only` call, both in the commit's own tree. Any other command makes no git call for this rule.
- A read that fails passes.
- The guard reads the index before the command runs. So in a chain, an earlier `git add <paths>` or `git rm <paths>` adds those paths to the commit and takes them out of the left-out set, and the check still runs. `git rm x && git commit` is the incident's own form.
- A left-out path that a later `git add <paths>` in the same command stages, with a commit after it, is not left behind. That is a deliberate split into two commits, so the earlier commit passes.
- An add or rm that names a folder, a glob, `.` or a variable is not read, and the commit passes.
- Any other earlier git call that changes the index (`add -A`, `add .`, `add -u`, `reset`, `restore --staged`) makes the commit pass: its effect is not read.
- A path that is staged and also has unstaged changes (after `git add -p`) is in the commit, not left out.
- The staged read turns rename detection off, so a `git mv` out of a folder counts for both folders.
- It asks, and the owner's answer decides. In a chain, rule `ask-alone` refuses the call, as decision `ask-commands-run-alone` (a command that needs the owner's answer runs alone) holds; the same commit alone asks. An override lifts it.

The ask names the left-out paths, so the reader sees what stays behind. Remedy: `git add <path>` for an edit that belongs in this commit, or commit it on its own.

## The incident

On 2026-11-07, lane replay-profile-parts made commit 7ba74efd9 with only a `git rm` staged. A tracked edit to a decision record in the same folder stayed unstaged, and review caught it late.

## Harm it stops

A change ships without the edit that belongs with it, and the record or test that explains it lands later or never.

Kind: build
Plan: docs/decisions/commit-leaves-edit-unstaged.md#the-ruling (all)
