# o16: any repo can adopt this project's way of working (claude-settings part)

Cloud build thread brief. Build advisor (3), Oct 26. Base: main after #615 (o2, one layout for
every repo) merges, so new files land where lint/layout.json says; the dispatcher names the commit.
Never rebase onto main after review. Push roadmap edits to the branch only; only "Triage the
roadmap (3)" republishes the roadmap page.

## Task

Package this project's operating model in claude-settings as templates, one skill and docs, so a
repo can adopt it later. Adopting it in any other repo is deferred for shiv: do not touch them.

What it packages (read the roadmap branch for the live source, never copy from memory):
- the standing roles: triage gatekeeper, build advisor and dispatcher, local liaison, merge hand;
  the roster and the counted hand-off rule (limits, slip trigger, hand-off file);
- autopilot deferral ("Deferred" lines; never wait on the owner);
- integration-branch batching (point at rule git-integration-branch-merge; do not restate it);
- the roadmap: roadmap/build.py and the roadmap/data layout (steps, topics, meta), briefs/ with
  the ask copy, handoffs/.

Sources: use the roadmap branch's handoffs/ and briefs/ and roadmap/build.py.
Name any rule you could not find a written source for.

Shape: one skill (for example skills/project-ops) that sets the model up in a repo, templates for
the roster, a brief and a hand-off, and a README section. Reuse roadmap/build.py by pointing at
it on the roadmap branch or moving one copy to main; never two copies (rule
building-one-home-per-capability), and say which you chose and why.

## Fences

- No change to any child repo. No new guard or gate.
- o8 (living roadmap page per repo) builds the page; this step packages the process around it.
  Do not design the page.

## Failure classes and proof

- A dry run: apply the skill to a scratch repo and show the files it writes; nothing it writes
  names this project's thread ids or people.
- Adds a skill whose instructions agents follow: a fresh Sonnet reviewer reads the diff.
- ste-changed through `verdict`.

## Report

Add one line, "Port to other repos: yes or no, and why" (shiv's ruling on c52, Oct 26). Cap 20
lines: Done, Deviations, Next. Send the green, reviewed head and branch to "Advise the
claude-settings build (3)". Do not merge, and do not rebase onto main. No question for shiv: park
any in the PR body.
