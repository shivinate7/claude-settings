---
name: project-ops
description: Use when the owner asks to give a repo session roles (coordinator, triage, batch runner), compaction of standing sessions, a roadmap record and briefs, or says "project-ops" or "adopt the way of working". Makes the record branch and gives the role, roster, brief and handoff templates. Not for ordinary code edits.
---

This skill packages the way the claude-settings project on claude.ai works, so another repo can
adopt it. The owner decides when a repo adopts it. Never set it up in a repo without the owner's grant.

The model assumes a claude.ai project: one coordinator session per repo starts every other
session. It starts triage and the batch runner together, as a trio, before any lane.
Without a project, each session holds one or more roles, and the owner acts as the coordinator.

## What it packages

- **Session roles.** The coordinator, triage, the batch runner, the arbiter and lanes.
  `templates/operating-model.md` says what each role owns. Triage, the batch runner and the arbiter
  compact in routine use and are not replaced. The coordinator rotates a standing session only when it
  goes stale or breaks. The coordinator compacts in place and has no successor (owner, 2026-11-10 14:29 CST, G7, standing sessions compact).
- **The roster.** One list of who holds each standing session now. `templates/roster.md`.
- **Autopilot.** An act that needs the owner's answer gets a "Deferred" line and waits. All other
  work runs. `templates/operating-model.md`.
- **Batching.** Until the cutover, rule `git-integration-branch-merge` (lanes join one integration branch) governs it.
  After the cutover, each lane PR merges alone on its own green run (decision `all-repos-switch-together`).
  The model adds only a review record on each PR (`templates/operating-model.md`, record
  `pr-review-record`). Under a standing merge grant, the batch runner batches each PR whose review record
  is done, as `merge --reviewed` finds it, and merges the integration PR on green (until the cutover; after it, each lane PR on green). The owner is not
  asked.
- **The record branch.** An orphan branch, `roadmap` by default, that holds the roadmap data,
  briefs and role handoff notes. It is never merged into main. A fork names its own record branch,
  such as `roadmap-<fork>`, in the extras key `record-branch`. For a fork's page, see skill
  `waiting-page`, "Make a repo's page".
- **The outbox.** `roadmap/outbox/`, one file per session, for non-urgent notes to triage. Its
  README gives the format. `templates/operating-model.md` says when to message instead.
- **Briefs and role handoffs.** `templates/brief.md` and `templates/role-handoff.md`. `scripts/brief_from_step.py <step>`
  fills the brief from a step file and the rulings that name it.

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
4. **Fill the tiers.** Copy `templates/operating-model.md` into the project's instructions on
   claude.ai. Fill each `<placeholder>`. The roster (`templates/roster.md`) lives on the record branch,
   written by triage (ruling R22).
5. **Triage pushes the record branch.** The guard lets only the triage session push it (rule
   `roadmap-one-writer`, the record branch's one writer). The coordinator starts triage before any other
   session (decision `session-tiers`). Send triage the repo and the branch name. Triage does steps 2 and 3
   in its own worktree, then commits and pushes the branch. The push needs no PR and runs no CI.
6. **Protect the default branch.** Name the one check the repo's CI reports (the `all-jobs-passed` rollup). Preview, then set, once the
   owner confirms the act (it changes the live repo):
   `python3 ~/.claude/skills/project-ops/scripts/protect.py --repo <owner>/<name> --check all-jobs-passed [--branch main]`,
   then the same with `--confirm`. It sets a ruleset on the branch: the one check, deletion and force-push blocked, and the Admin role able to bypass on pull requests only. It refuses any `--check` other than `all-jobs-passed`, and more than one, so no repo starts with none (decision `same-check-kinds`). It never touches classic protection. merge reads the required checks from the ruleset first, then from classic protection, so keep `merge.requiredChecks` at `"protection"`.
7. **Add the PR template.** If the adopting repo has no `.github/pull_request_template.md`, copy
   `templates/pull_request_template.md` to that path. Put it in by a pull request on the repo's default
   branch, never on the record branch. The template holds the two PR-body lines the merge tool reads:
   `Retire-run:` (a debt close with no runnable check) and `Drops-lines:` (lines dropped on purpose).
   The file sits twice on purpose: GitHub reads only the copy under `.github/`, and this skill ships the copy under `templates/`.
   If the file exists, leave it, and report whether it holds both lines.
8. **Report** the record branch, the files written, the ruleset set, each placeholder the owner must still fill, and whether the PR template was added or already present.

## The roadmap block

`skills/roadmap` is the one home for building the roadmap block, for any checkout. This skill
keeps no copy. Its `SKILL.md` says how to build (`--block`) and what `--live` passes. The build
publishes nothing: the page writer splices the block into the repo's one page and alone
publishes it (skill `waiting-page`). At triage start, when the repo has no waiting page, triage makes
it, with no separate grant (skill `waiting-page`, "Make a repo's page"). The scaffolded `roadmap/README.md`
(`templates/record-branch/roadmap/README.md.tmpl`) holds the step file shape.
An adopting repo keeps its record in `roadmap/data/` on the record branch, and the roadmap build script
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

- `git-integration-branch-merge`: how lanes join a batch and how a red batch drops a lane, until the cutover. After it, each lane PR merges alone, and a red main reverts the blamed lane (decision `no-merge-onto-red-main`).
- `roles-review-cap-three`: review rounds.
- `speak-cite-id-plus-gloss`: give every id a plain name.
- `parallelism-no-mid-task-talk`: lanes do not talk mid-task.
