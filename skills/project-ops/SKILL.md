---
name: project-ops
description: Use when the owner asks to give a repo session tiers (coordinator, triage, batch runner), rotation by usage tally, a roadmap record and briefs, or says "project-ops" or "adopt the way of working". Makes the record branch and gives the role, roster, brief and handoff templates. Not for ordinary code edits.
---

This skill packages the way the claude-settings project on claude.ai works, so another repo can
adopt it. The owner decides when a repo adopts it. Never set it up in a repo without the owner's grant.

The model assumes a claude.ai project: one coordinator session per repo starts every other
session. It starts triage and the batch runner together, as a trio, before any lane session.
Without a project, each tier is one Claude Code session, and the owner acts as the coordinator.

## What it packages

- **Session tiers.** The coordinator, triage, the batch runner and lane sessions.
  `templates/operating-model.md` says what each tier owns, and how triage and the batch runner
  rotate by a usage tally. The coordinator compacts in place and has no successor.
- **The roster.** One list of who holds each standing session now. `templates/roster.md`.
- **Autopilot.** An act that needs the owner's answer gets a "Deferred" line and waits. All other
  work runs. `templates/operating-model.md`.
- **Batching.** Rule `git-integration-branch-merge` (lanes join one integration branch) governs it.
  The model adds only the "frozen at <sha>" line on each merge run and a fixed form for each merge go
  (`templates/operating-model.md`, "Autopilot"). Under a standing merge grant,
  the coordinator gives each merge go, and the batch runner runs the merge tool on it. The owner is not asked.
- **The record branch.** An orphan branch, `roadmap` by default, that holds the roadmap data,
  briefs and role handoff notes. It is never merged into main. A fork names its own record branch,
  such as `roadmap-<fork>`, in the extras key `record-branch`. For a fork's page, see skill
  `waiting-page`, "Make a repo's page".
- **The outbox.** `roadmap/outbox/`, one file per session, for non-urgent notes to triage. Its
  README gives the format. `templates/operating-model.md` says when to message instead.
- **Briefs and role handoffs.** `templates/brief.md` and `templates/role-handoff.md`.

A role handoff note and a session handoff are two cases of one meaning: notes one holder writes so the next
reader can continue (GLOSSARY.md, "handoff"). A session handoff is the notes file of one session
under `~/.claude/handoffs/`. A role handoff note is a file in the record branch's `handoffs/` folder
that triage or the batch runner writes for its successor.

## Steps

1. **Get the owner's grant.** Name the repo and the record branch. When the owner has not named the repo, stop.
2. **Make the record branch.** In a new worktree of the repo, make an orphan branch:
   `git worktree add --orphan -b <branch> ../<repo>-<branch>` (git 2.42 or later).
3. **Write the skeleton.** From the repo root of that worktree:
   `python3 ~/.claude/skills/project-ops/scripts/scaffold.py --dest . --repo <owner>/<name> --branch <branch>`.
   It writes `CLAUDE.md`, `roadmap/README.md`, `roadmap/outbox/README.md` and the empty folders `roadmap/data/steps`,
   `roadmap/data/topics`, `roadmap/data/meta`, `briefs` and `handoffs`. It prints each path it
   writes. It refuses, and writes nothing, when one of those files exists.
4. **Fill the tiers.** Copy `templates/operating-model.md` and `templates/roster.md` into the
   project's instructions on claude.ai. Fill each `<placeholder>`. The roster's home is the project
   instructions, so keep no second copy in the repo.
5. **Commit and push** the record branch. It needs no PR and runs no CI.
6. **Protect the default branch.** Name the checks the repo's CI reports. Preview, then set, once the
   owner confirms the act (it changes the live repo):
   `python3 ~/.claude/skills/project-ops/scripts/protect.py --repo <owner>/<name> --check <name> [--check <name> ...] [--branch main]`,
   then the same with `--confirm`. It refuses an empty list, so no repo starts with none. merge reads the
   required checks from this protection, so keep `merge.requiredChecks` at `"protection"`.
7. **Report** the record branch, the files written, the protection set, and each placeholder the owner must still fill.

## The roadmap block

`skills/roadmap` is the one home for building the roadmap block, for any checkout. This skill
keeps no copy. Its `SKILL.md` says how to build (`--block`) and what `--live` passes. The build
publishes nothing: the waiting-page writer splices the block into the repo's one page and alone
publishes it (skill `waiting-page`). At triage start, when the repo has no waiting page, triage makes
it, with no separate grant (skill `waiting-page`, "Make a repo's page"). The scaffolded `roadmap/README.md`
(`templates/record-branch/roadmap/README.md.tmpl`) holds the step file shape.
An adopting repo keeps its record in `roadmap/data/` on the record branch, and the builder
reads it there.

## Shared resources

Decision `shared-resource-owner` (a shared machine names one owning repo) governs this section.

- A shared machine has one owning repo. Its `.claude/layout-extras.json` lists the machine under
  `shared-resources` with the owner, the preflight path and the hold record path.
- Each user repo owns its own deploy and restart scripts. The owner repo owns only the preflight
  and the hold record.
- Before a deploy, a restart or a bulk import, run the owner's preflight and read its holds.
  A hold stops the act.
- A user repo that needs a change to the preflight or the holds writes a handoff to the owner
  repo's session: a note in the owner's outbox on its record branch. It never edits the owner's
  files. It never overrides the owner's guard.

## Rules this skill does not restate

- `git-integration-branch-merge`: how lanes join a batch and how a red batch drops a lane.
- `roles-review-cap-three`: review rounds.
- `speak-cite-id-plus-gloss`: give every id a plain name.
- `parallelism-no-mid-task-talk`: lanes do not talk mid-task.
