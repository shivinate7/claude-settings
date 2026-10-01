# Plan: the shared merge tool

One command merges a pull request in every repo. It claims record numbers before the merge.
It waits for CI on the claim commit. It reverts the claim when a step fails. Then it merges.
This plan is a design. It builds nothing.

## Why

CLAUDE.md rule `git-slug-then-claim-number` says: claim the number at merge. Two tools do it
now, in two orders.

- `actions/stamp` claims after the merge, on the default branch. Only q_max uses it. Between
  the merge and the stamp, main holds a pending record.
- Banchi's `make merge` (`scripts/merge-pr.py` and `scripts/claim-ids.py`) claims before the
  merge, on the pull request branch, and waits for CI on that commit (Banchi D140, merge
  claims the decision number).

Banchi DEBT78 (the merge flow belongs in claude-settings) holds the owner's ruling. Before-merge
becomes the default for every repo. Main never holds a slug, and a failed claim never reaches
main. claude-settings never goes private, so its `actions/` stay callable from every repo.

## The interface

A command, and the existing action in `check` mode. No new action.

```
merge <pr>              preview: what it would claim and merge. Presses nothing.
merge <pr> --confirm    claim, push, wait, merge, then sync the local main.
merge --unlock          remove this repo's merge lock. Reads no other state.
```

The command is `merge/merge.py`, Python stdlib plus `gh`, `git` and `node`. It calls
`actions/stamp/stamp.mjs` for every record read and write. It has no parser of its own.

The action keeps mode `check`. Every pull request runs it. Every push to the default branch
runs it too, and there it refuses any pending record (see "q_max and the stamp action").

### How a repo opts in

The repo keeps one config file, the stamp config it already has or a new one at
`.github/stamp.json`. A `merge` block holds the merge fields. One file, one home.

```json
{
  "defaultBranch": "main",
  "kinds": [ "... the stamp kinds, unchanged ..." ],
  "regenerate": "python3 scripts/index-decisions.py --write",
  "merge": {
    "method": "merge",
    "requiredChecks": "protection",
    "deadlineMinutes": 45,
    "afterMerge": ["python3 scripts/primary_sync.py --confirm"],
    "deleteBranch": true
  }
}
```

| Field | Meaning |
|---|---|
| `kinds` | The id kinds and their record folders, as the stamp README states them. A repo with no records writes `[]`, and the claim step does nothing. |
| `regenerate` | The repo's own generator. It runs after the claim, in the same commit. It moves here from the action input, so the command and the action read one value. |
| `cite.glossFirstUse` | New, shape 3. Globs, such as `["CLAUDE.md"]`. At a claimed cite's first use in a paragraph, the claim adds ` (gloss)`, the first six words of the record title. Shapes 1 and 2 already have `{gloss}` in `cite.template`. |
| `merge.method` | `merge`, `squash` or `rebase`. Read it from the repo history. Never guess it. |
| `merge.requiredChecks` | `"protection"` reads the branch protection API. A list names the checks for a repo with no protection. |
| `merge.deadlineMinutes` | The longest wait for the claim commit's checks. |
| `merge.afterMerge` | Commands that run after the local main moves, such as a primary-checkout sync. Each runs in the repo root. A failure is reported, and the merge stays. |
| `merge.deleteBranch` | Delete the head branch on origin and locally after the merge. |

A repo calls the command from its own wrapper, such as a `make merge` target. The wrapper
passes its arguments through and adds nothing.

## The flow

1. Take the merge lock for this repo (see "Failure modes").
2. Fetch origin. Read the pull request head SHA, base and mergeable state through `gh`.
   Refuse a CONFLICTING or DIRTY pull request before any claim.
3. Make a detached temporary worktree at the head SHA. The caller's checkout is never
   touched, and the claim reads exactly the tree that merges.
4. Run `stamp.mjs --claim --base origin/<defaultBranch>`. The ceiling is every number in the
   tree and in the base tip, plus each `RETIRED` list. Then run `regenerate`.
5. When nothing changed, skip to step 8. Else commit with the trailer
   `Record-claim: <ids>` and push `HEAD:<branch>` as a plain push. Never force.
6. Wait for the required checks on the claim SHA. Each minute, read the mergeable state and
   the head SHA.
7. Fetch the base again. Run `stamp.mjs --check` against the base tip. Each claimed number
   must still be free there.
8. Run `gh pr merge <pr> --<method> --match-head-commit <sha>`. Never `--admin`.
9. Fast-forward the local main to the merge commit that origin holds: in the worktree that
   holds main, or by `git fetch origin main:main` when none does. Then run `afterMerge`.
10. Delete the head branch, remove the temporary worktree, and release the lock.

A rerun finds its own claim at the head (the trailer, and each number still free) and resumes
at step 6. It does not claim twice.

## Failure modes

| Failure | Guard |
|---|---|
| Two sessions claim against one base tip. | The merge lock serializes claim to merge for one repo. Step 7 reads the base tip again before the merge. After the merge, `check` on the default branch refuses a duplicate number. |
| A required check on the claim commit goes red. | Revert the claim commit and push the revert. Do this only while the origin head is the claim SHA. Nothing merges. The message names the red check. |
| The branch goes DIRTY or CONFLICTING in the wait. | The minute read sees it. The wait stops, and the claim is reverted as above. The message says to merge the base into the branch and run again. |
| Someone pushes or force-pushes the branch in the wait. | The head SHA is not the claim SHA. The tool reverts nothing, because the claim commit can be gone. `--match-head-commit` refuses the merge in any case. The message says to run again. |
| A push of the claim or of the revert is refused. | Each push is fast-forward only, so a moved branch refuses it. Nothing is on origin. The tool removes its worktree and stops. A refused revert prints the exact revert command. |
| Protection refuses the merge. | `gh pr merge` fails. The claim is reverted, and the full gh message is printed. The tool never adds `--admin` and never pushes the default branch. |
| The tool stops mid-run. | The lock carries an expiry of `deadlineMinutes` plus ten. A rerun breaks an expired lock. `merge --unlock` removes the lock and reads nothing first. |

The pull request check needs one change. Off the default branch, `check` refuses a number
the branch added. It must accept a number that a `Record-claim` commit added, when that
number is free on the base tip. A number with no trailer stays refused.

## What moves out of Banchi

These parts of `scripts/merge-pr.py` are generic, and they move into `merge/merge.py`:

- the claim half, the check wait, and the required-contexts read
- the mergeability poll and the rollback
- the GitHub half, which gains `--match-head-commit`
- the local half that moves main, and the branch cut

These parts of `scripts/claim-ids.py` move into `stamp.mjs`: the claim, the stale read
(step 7), the debt kind, and the first-use gloss. A debt is a heading kind whose file name
has no letter. The gloss replaces `entry_gloss` and `gloss_first_uses`.

Stays in Banchi:

- `scripts/githooks/reference-transaction` and `pre-push`. The tool never moves main except to
  a commit origin holds, which allow rule 3 already permits.
- `scripts/primary_sync.py`, called through `afterMerge`.
- Its generators, called through `regenerate`: the decision index, the `docs/map.py`
  renumber, and the derived tests page.
- Build steps, numbered by hand and refused through `unclaimed`
  (deferred `banchi-build-steps`).
- The docs-audit `id claims` row, and the rule that only a named Orchestrator merges.

Banchi then calls the tool from `make merge`, and runs mode `check` in `check.yml`. It deletes
`scripts/merge-pr.py` and the claim path of `scripts/claim-ids.py`. It deletes the matching
arms of `claim-selftest.py` and `merge-selftest.sh`. That closes DEBT78. D140 is rewritten in
place to name the shared tool. Its ruling does not change.

## q_max and the stamp action

q_max stamps after the merge through `stamp.yml`, mode `stamp`. It moves in its own repo, by
its own session, per `record-stamp-stays-generic`, the stamp stays generic:

1. Add the `merge` block and move `regenerate` into the config.
2. Merge through the command.
3. Switch `stamp.yml` to mode `check` on a push to main, with `contents: read`. The write
   permission and the protection bypass it needed go away.

After the move, no repo uses mode `stamp`. Question 3 asks whether to delete it.

## Build lanes

Each lane is one Sonnet builder. Each lane waits for the lane above it, except lanes 4 and 5.

| # | Lane | Done when |
|---|---|---|
| 1 | `stamp.mjs`: `--claim --base`, the base-tip ceiling, the `Record-claim` exception in `check`, the default-branch refusal of any pending record, `regenerate` in the config. | New `test_stamp.mjs` cases pass, and each new refusal goes red on a mutant. |
| 2 | `stamp.mjs`: the debt kind and `cite.glossFirstUse`. | `test_stamp.mjs` passes. A claim on a copy of Banchi main matches `claim-ids.py --write` byte for byte, debts and gloss included. |
| 3 | `merge/merge.py`, git half: lock, temporary worktree, claim, push, revert, resume, `--unlock`, local main, `afterMerge`. Land `merge/` in `landed-dirs.txt` and the guard's frozen list. | `merge/test_merge.py` against a local bare origin covers the race, a moved head, a refused push and a stopped run. Wired into `gates.yml`. |
| 4 | `merge/merge.py`, GitHub half: required checks, the wait, the minute read, `gh pr merge --match-head-commit`, branch delete. | The same test, with a `gh` shim on `PATH`, covers red, DIRTY, a force-push and a protection refusal. |
| 5 | Docs: the stamp README contract and adoption checklist, the claude-settings README, `rule_mechanisms.json` for `git-slug-then-claim-number`. | `rule_audit.py`, `check_landed_dirs.py` and STE lint pass. |
| 6 | Banchi, in Banchi: the config, mode `check` in `check.yml`, `make merge` on the tool. | One real merge through the tool. `make check` is green. |
| 7 | Banchi, in Banchi: delete the ported code, the gloss stopgap and DEBT78. Rewrite D140. | `make check` is green. A search for `entry_gloss` and `gloss_first_uses` finds nothing. |
| 8 | q_max, in q_max: the three steps above. | One real merge through the tool. `stamp.yml` holds no write permission. |

## Open questions for the owner

1. **How the installed command reaches `stamp.mjs`.** `landed-dirs.txt` lands no `actions/`.
   A: land `actions/` too. B: the command fetches `stamp.mjs` at a pinned SHA into a cache.
   C: move the engine into `merge/` and point the action at it.
   **Recommend A.** One copy, and the installer already lands folders.
2. **Where the merge lock lives.** A: a file lock on this machine. B: a ref on origin,
   `refs/merge-lock/<branch>`, made by the GitHub API, which refuses a ref that exists.
   **Recommend B.** Cloud sessions merge too, and a file lock cannot see them.
3. **Mode `stamp` after q_max moves.** A: delete it. A pending record on main then goes red in
   `check`, and the fix is any pull request through the command, which claims it. B: keep it
   as an opt-in fallback. **Recommend A.** One path, and no workflow that writes to main.
4. **An installed command behind claude-settings main.** Banchi refuses a stale copy of its
   own merge script. A: the command refuses when its install is behind origin. B: it warns.
   C: nothing. **Recommend A.** The command moves main, so a stale copy is the costly case.
