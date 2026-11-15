# A one-time cleanup of stale prose waits for its mechanical check

## The question

A repo holds stale prose. May a session clean it up once, by hand, before a check exists that keeps that prose fresh?

## The ruling

Owner ruling `own-mechanical-before-cleanup` (the ruling file on the `roadmap` ref, `roadmap/rulings/own-mechanical-before-cleanup.json`), 2026-11-15 11:07 CST, relayed verbatim by the consultant. The ruling file holds the owner's words, so this record quotes them from there:

> "it doesnt get its one time bandaids it needs the mechanical fixes first so that way the one time cleanup doesnt result in things immediately going stale again"

The ruling file's longer text adds the owner's earlier words: a one-time cleanup is fine "if the mechanical fix going forwards has landed". The file keeps that text, so this record does not repeat it.

## What it decides

- The order is: the check first, then the one-time cleanup.
- Where a check has landed, the one-time cleanup may run.
- Where no check has landed, the session builds the check first. The cleanup waits.

The owner wrote "stuff" and "stale prose". This record reads the ruling as binding one-time cleanups of stale prose only. That scope is the lane brief's reading, not the owner's.

## What counts as "the check landed"

- A check merged on main that would have turned red on the drift the cleanup removes.
- In a child repo, the check is the shared action `actions/claude-md-cites`, at a pin at or after the commit that holds it (decision `child-cites-not-copies`, a child repo names a record and never copies it).

A check on a branch, in a draft, or in a plan has not landed.

## How a session applies it

1. Before a cleanup lane starts, name the drift it removes and the check that would have caught it.
2. If that check has not landed, park the cleanup as a draft. Start no new work on it.
3. Start one lane per missing check. The cleanup resumes after that check merges.

Incidents the ruling answers:

- 2026-11-15 09:01 CST: a switch that every repo must make together drifted, and the repos did not stay aligned. No check read it.
- At least four cleanup lanes were open when the owner ruled: pull request #3504 in claude-settings, and the draft cleanups in mailaudit, banchi and ios-adblock.

## What it does not cover

- A ruling record, such as ios-adblock pull request #172. A ruling record keeps the owner's words as filed. It is not stale prose.
- A pull request that applies a ruling filed today to the record that the ruling overtakes. That is the normal rewrite in place (rule `speak-rewrite-superseded-in-place`), not a cleanup.

The lane brief gives both as the consultant's order. The wave plan on the `roadmap` ref sources only the first, as the consultant's 11:15 CST reading. No file sources the second, so it is the brief's reading. Neither is the owner's. The owner has not ruled on them.

## Consultant's reading

Labelled paraphrase, 2026-11-15 11:08 CST. These are the consultant's words as the coordinator quoted them. This lane did not read them at their source. A one-time cleanup of stale prose runs only after the mechanical check that keeps it fresh has landed. Without that check, build the check first, then do the cleanup.

Coordinator's application, 2026-11-15 11:10 CST, a pick the owner did not type: hold each open cleanup that has no check as a draft, and start one lane per missing check.

## Open

- The record-versus-later-ruling check is another lane: step `record-vs-later-ruling-check`. It is the mechanical home that would show a record that a later ruling overtook. Until it lands, a cleanup of that drift waits under this ruling.
- Nothing yet checks that a cleanup lane names its check. A session applies this record by reading it.
- Lines of the owner's `CLAUDE.md` files may need to name this order. A parent session proposes them. This lane edits none.

Kind: process
Home: skills/fresh-prose/SKILL.md
