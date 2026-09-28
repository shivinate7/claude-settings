# The record stamp stays generic

`actions/stamp` names no repo. It describes record shapes, config fields, and a contract. Each
repo reads its own tree and writes its own config. The parent carves out no exception for one
repo.

## The ruling

On 2026-09-28 the owner said: "I think moreso you need to remain generic and provide me briefs
that allow each of the repos to individually get compliant, rather than carving out exceptions
for each repo."

This changes one part of `one-shared-record-stamp`, one shared parser. That entry keeps its
choice: one engine, and a config file in each repo's own tree. It loses its per-repo parts.
Those are the example configs named after repos, the README's per-repo notes, and any engine
branch that exists for one repo alone.

## Why

A parent that holds one repo's facts goes stale when that repo changes. Nothing in the parent
reads the repo again, so the stale fact stays and looks true. A repo that reads its own tree at
adoption time cannot hold a stale copy of itself.

## What changes

- The example configs are named for the shape they show, never for a repo.
- The README states the contract that any adopting repo meets, and the checks that prove it.
- A behavior that only one repo needs becomes a config field with a generic name, or the
  engine drops it.
- One adoption brief serves every repo. The repo's own session measures its own fields.

## The gap closed at the same time

`--check` did not refuse a record numbered on a branch. MEASURED on 2026-09-24 and again on
2026-09-28 against `main`: a feature branch that adds a record with `id: D-002` passes
`--check` with exit 0. The engine asked its only branch question on the default branch, and
that question is about a stale pending record. The same change adds the refusal off the
default branch, against the base branch's tree.

## What would reopen this

A shape that no config field can state without naming one repo. Bring that shape to the owner
as a question. Do not add a repo name to the parent to fit it.
