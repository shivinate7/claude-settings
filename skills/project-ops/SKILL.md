---
name: project-ops
description: Use when the owner asks to give a repo standing roles, counted hand-offs, a roadmap record and briefs, or says "project-ops" or "adopt the way of working". Makes the record branch and gives the role, roster, brief and hand-off templates. Not for ordinary code edits.
---

This skill packages the way the claude-settings project on claude.ai works, so another repo can
adopt it. The owner decides when a repo adopts it. Never set it up in a repo without the owner's word.

The model assumes a claude.ai project: a coordinator session in the project chat starts one thread
per role. Without a project, each role is one Claude Code session, and the owner acts as the coordinator.

## What it packages

- **Standing roles.** Triage, build advisor, local liaison and merge hand. `templates/operating-model.md`
  says what each role owns and the hand-off rule that replaces it.
- **The roster.** One list of who holds each role now. `templates/roster.md`.
- **Autopilot.** A step that needs the owner's answer gets a "Deferred" line and waits. All other
  work runs. `templates/operating-model.md`.
- **Batching.** Rule `git-integration-branch-merge` (lanes join one integration branch) governs it.
  The model adds only the "frozen at <sha>" line on each merge go.
- **The record branch.** An orphan branch, `roadmap` by default, that holds the roadmap data,
  briefs and role hand-off notes. It is never merged into main.
- **Briefs and role hand-offs.** `templates/brief.md` and `templates/role-handoff.md`.

A role hand-off note is not a session handoff. A session handoff is the notes file of one session
under `~/.claude/handoffs/` (GLOSSARY.md, "handoff"). A role hand-off note is a file in the record
branch's `handoffs/` folder that a standing role writes for its successor.

## Steps

1. **Get the owner's word.** Name the repo and the record branch. When the owner has not named the repo, stop.
2. **Make the record branch.** In a new worktree of the repo, make an orphan branch:
   `git worktree add --orphan -b <branch> ../<repo>-<branch>` (git 2.42 or later).
3. **Write the skeleton.** From the repo root of that worktree:
   `python3 ~/.claude/skills/project-ops/scripts/scaffold.py --dest . --repo <owner>/<name> --branch <branch>`.
   It writes `CLAUDE.md`, `roadmap/README.md` and the empty folders `roadmap/data/steps`,
   `roadmap/data/topics`, `roadmap/data/meta`, `briefs` and `handoffs`. It prints each path it
   writes. It refuses, and writes nothing, when one of those files exists.
4. **Fill the roles.** Copy `templates/operating-model.md` and `templates/roster.md` into the
   project's instructions on claude.ai. Fill each `<placeholder>`. The roster's home is the project
   instructions, so keep no second copy in the repo.
5. **Commit and push** the record branch. It needs no PR and runs no CI.
6. **Report** the record branch, the files written, and each placeholder the owner must still fill.

## The roadmap page

The page builder has one home: `roadmap/build.py` on the `roadmap` branch of claude-settings. This
skill points at it and keeps no copy. Today the builder reads only its own branch's `roadmap/data/`,
and its viewer names claude-settings. The claude-settings roadmap step "a living roadmap page for
every repo" makes the page read any repo's data. Until it lands, an adopting repo keeps its record
in `roadmap/data/` with the same file shape, and has no page.

Each step file is `roadmap/data/steps/<id>.json`, with the fields `title`, `status` (`todo`,
`active`, `done`), `phase`, `order`, `why`, `note`, `ask` and `updatedAt`. A topic file in
`roadmap/data/topics/` holds reference facts. `roadmap/data/meta/` holds page-wide data such as phases.

## Rules this skill does not restate

- `git-integration-branch-merge`: how lanes join a batch and how a red batch drops a lane.
- `roles-review-cap-three`: review rounds.
- `speak-cite-id-plus-gloss`: give every id a plain name.
- `parallelism-no-mid-task-talk`: lanes do not talk mid-task.
