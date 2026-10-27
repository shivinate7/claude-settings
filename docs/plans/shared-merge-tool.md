# Plan: the shared merge tool

One command, `merge`, merges a pull request in every repo. It claims record numbers on the
pull request branch before the merge. It waits for CI on the claim commit. It calls
`actions/stamp/stamp.mjs` for every record read and write.

The tool is built and in use. The code is the home of what it does. This plan holds the open
lanes and what Banchi still has to do.

## Where the built tool is written

- **Behaviour:** the code. `confirm` in `merge/merge.py` is the flow. `merge/launch.py` is the
  fresh-code guard. `bin/merge` finds the checkout and starts `merge/launch.py`.
  `bin/merge.cmd` starts `bin/merge` on Windows.
- **Rulings, usage and exit codes:** the claude-settings README, "The `merge` command". It
  lists each decision with a gloss.
- **What an adopting repo does:** `actions/stamp/README.md`, "The merge tool contract".

## Why

CLAUDE.md rule `git-slug-then-claim-number` says: claim the number at merge. Banchi D140 (merge
claims the decision number) set the order. The claim runs on the pull request branch, before
the merge, and waits for CI on that commit.

Banchi DEBT78 (the merge flow belongs in claude-settings) holds the owner's ruling. Before-merge
is the default for every repo. Main never holds a slug, and a failed claim never reaches main.
claude-settings never goes private, so its `actions/` stay callable from every repo.

## Open lanes

Both lanes run in the Banchi repo.

| # | Lane | Waits for | Done when |
|---|---|---|---|
| 6 | The config, mode `check` in `check.yml`, and `make merge` on the tool. | none | One real merge through the tool. `make check` is green. |
| 7 | Delete the ported code, the gloss stopgap and DEBT78. Rewrite D140. | 6 | `make check` is green. A search for `entry_gloss` and `gloss_first_uses` finds nothing. |

## What moves out of Banchi

These parts of `scripts/merge-pr.py` moved into `merge/merge.py`:

- the claim half, the check wait, and the required-contexts read
- the mergeability poll and the rollback
- the GitHub half, which gained `--match-head-commit`
- the local half that moves main, and the branch cut

These parts of `scripts/claim-ids.py` moved into `stamp.mjs`: the claim, the stale read, the
debt kind, and the first-use gloss. A debt is a heading kind whose file name has no letter.
The gloss replaces `entry_gloss` and `gloss_first_uses`.

Stays in Banchi:

- `scripts/githooks/reference-transaction` and `pre-push`. The tool never moves main except to
  a commit origin holds, which allow rule 3 already permits.
- `scripts/primary_sync.py`, called through `afterMerge`.
- Its generators, called through `regenerate`: the decision index, the `docs/map.py`
  renumber, and the derived tests page.
- Build steps, numbered by hand and refused through `unclaimed`
  (debt `banchi-build-steps`).
- The docs-audit `id claims` row, and the rule that only a named Orchestrator merges.

Banchi then calls the tool from `make merge`, and runs mode `check` in `check.yml`. It deletes
`scripts/merge-pr.py` and the claim path of `scripts/claim-ids.py`. It deletes the matching
arms of `claim-selftest.py` and `merge-selftest.sh`. That closes DEBT78. D140 is rewritten in
place to name the shared tool. Its ruling does not change.
