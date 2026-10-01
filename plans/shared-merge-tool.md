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

### How the command finds claude-settings

No install step copies the tool. It runs from the claude-settings checkout that the device
already uses as its parent mandate. `actions/stamp` sits beside it in that checkout.

The only file outside the checkout is a shim, `~/.claude/bin/merge`, of about ten lines. The
shim finds the checkout and starts `merge/merge.py` there. It holds no merge logic, so it
never needs an update. A repo's own wrapper can hold the same lookup instead of the shim.

The lookup, in this order:

1. `CLAUDE_SETTINGS_DIR`, when it is set.
2. The `@` include line in `~/.claude/CLAUDE.md`. The checkout is the folder of the included
   `CLAUDE.md`.
3. Neither found: a cloud session, or a device with no checkout. The shim clones
   `shivinate7/claude-settings` into a temporary folder. The repo is public, so no
   credential is needed.

Each result must be a git checkout whose `origin` is `shivinate7/claude-settings`. Any other
result stops the command before it reads a pull request.

### The fresh-code guard

The command runs claude-settings' current `main` when it can. It updates itself and never
refuses to merge for an old copy.

1. Fetch `origin main` in the checkout.
2. Run `merge.py` and `stamp.mjs` from a detached temporary worktree at the fetched
   `origin/main` SHA. The checkout's own tree is never written. So local edits and a dirty
   tree are safe.
3. When the checkout is on `main`, clean, and behind, fast-forward it. In any other state,
   leave it, and print one line that says why.
4. **Warn loudly, then go on.** When the command cannot prove fresh code (no network, a fetch
   failure, a SHA mismatch, or a dirty checkout), it runs the code it has. Before step 1 of the
   flow, it prints a warning block. The block names the SHA it runs, how many commits that SHA
   is behind `origin/main` when that is known, and why the update failed.

Each run prints the claude-settings SHA it ran. `merge --dev` runs the checkout's own tree
instead, for work on the tool itself. Only that flag does it.

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

1. Take the merge lock: create the ref `refs/merge-lock/<defaultBranch>` on origin through the
   GitHub API. The API refuses a ref that exists, so only one session holds it.
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

After the move, no repo uses mode `stamp`, and lane 9 deletes it. A pending record on main
then goes red in `check`. The fix is any pull request through the command, which claims it.

## Build lanes

Each lane is one Sonnet builder. When every lane in its "Waits for" cell has merged, a lane starts.

| # | Lane | Waits for | Done when |
|---|---|---|---|
| 1 | `stamp.mjs`: `--claim --base`, the base-tip ceiling, the `Record-claim` exception in `check`, the default-branch refusal of any pending record, `regenerate` in the config. | none | New `test_stamp.mjs` cases pass, and each new refusal goes red on a mutant. |
| 2 | `stamp.mjs`: the debt kind and `cite.glossFirstUse`. | 1 | `test_stamp.mjs` passes. A claim on a copy of Banchi main matches `claim-ids.py --write` byte for byte, debts and gloss included. |
| 3 | The shim, the lookup, the fresh-code guard and `--dev`. | none | `merge/test_launch.py` covers each lookup source, a dirty checkout left untouched, and an offline fetch that warns and runs the code it has. Each guard goes red on a mutant. Wired into `gates.yml`. |
| 3b | `merge/merge.py`, git half: the lock ref, temporary worktree, claim, push, revert, resume, `--unlock`, local main, `afterMerge`. | 1 | `merge/test_merge.py` against a local bare origin covers the race, a moved head, a refused push and a stopped run. Wired into `gates.yml`. |
| 4 | `merge/merge.py`, GitHub half: required checks, the wait, the minute read, `gh pr merge --match-head-commit`, branch delete. | 3b | The same test, with a `gh` shim on `PATH`, covers red, DIRTY, a force-push and a protection refusal. |
| 5 | Docs: the stamp README contract and adoption checklist, the claude-settings README, `rule_mechanisms.json` for `git-slug-then-claim-number`. | 1, 2, 3, 4 | `rule_audit.py`, `check_landed_dirs.py` and STE lint pass. |
| 6 | Banchi, in Banchi: the config, mode `check` in `check.yml`, `make merge` on the tool. | 2, 3, 4 | One real merge through the tool. `make check` is green. |
| 7 | Banchi, in Banchi: delete the ported code, the gloss stopgap and DEBT78. Rewrite D140. | 6 | `make check` is green. A search for `entry_gloss` and `gloss_first_uses` finds nothing. |
| 8 | q_max, in q_max: the three steps above. | 3, 4 | One real merge through the tool. `stamp.yml` holds no write permission. |
| 9 | Delete mode `stamp` from `actions/stamp`, its tests and its README. | 8 | No workflow in any repo names mode `stamp`. `test_stamp.mjs` passes, and a pending record on the default branch goes red in `check`. |

## Settled by the owner

1. **No install.** The command runs from the claude-settings checkout that every device's
   `~/.claude/CLAUDE.md` includes. `actions/stamp` sits beside it, so `landed-dirs.txt` needs
   no `actions/`.
2. **The merge lock is a ref on origin,** `refs/merge-lock/<branch>`, made by the GitHub API.
   Cloud sessions merge too, and a file lock cannot see them.
3. **Delete mode `stamp` once q_max moves** (lane 9). One path, and no workflow writes to main.
4. **The command updates itself before every merge.** It never refuses to merge for an old
   copy. When it cannot prove fresh code, it warns loudly and goes on (see "The fresh-code
   guard").

## Open question for the owner

1. **Should `--dev` exist?** It runs the checkout's own tree, for work on the tool itself.
   A: yes, behind the explicit flag only. B: no, and the tool is tested through its own suites.
   **Recommend A.** Without it, each edit to the tool needs a merge to main before a real run.
