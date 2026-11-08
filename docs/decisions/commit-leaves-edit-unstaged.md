# A commit asks when it leaves a tracked edit behind beside a staged change

## The ruling

Coordinator, 2026-11-07 17:31 CST, to lane resumed-agent-stale-tree: warn, not refuse. Orchestrator's call, not an owner grant: the form and the read.

The guard rule `commit-leaves-edit-unstaged` asks before a `git commit` when a tracked file is modified in the work tree but left out of the commit, and a file in the same folder is in the commit.

- Only a plain `git commit` with no `-a`, no `--only`, `-o`, `-i` and no named paths is read. Those forms choose their files on purpose.
- In the commit: each path that differs between the index and HEAD. Left out: each tracked path whose work-tree copy differs from the index. Untracked files do not count.
- Same folder: the two paths share their parent folder. An edit left out in another folder passes.
- `--amend` and `--dry-run` are read the same way and pass the same way.
- One `git diff --cached --name-only` and one `git diff --name-only` call, both in the commit's own tree. Any other command makes no git call for this rule.
- A read that fails passes.
- It asks, and the owner's answer decides. An override lifts it.

The ask names the left-out paths, so the reader sees what stays behind. Remedy: `git add <path>` for an edit that belongs in this commit, or commit it on its own.

## The incident

On 2026-11-07, lane replay-profile-parts made commit 7ba74efd9 with only a `git rm` staged. A tracked edit to a decision record in the same folder stayed unstaged, and review caught it late.

## Harm it stops

A change ships without the edit that belongs with it, and the record or test that explains it lands later or never.

Kind: build
Plan: docs/decisions/commit-leaves-edit-unstaged.md#the-ruling (all)
