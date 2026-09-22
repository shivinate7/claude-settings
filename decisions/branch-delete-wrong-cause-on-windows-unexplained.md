# The branch-delete `-D` mutant's Windows wrong-cause stays unexplained

## What was measured

Real Windows CI (`gates-windows`, run 35673561218, commit e7aa11e) ran
`hooks/mutate_guard.py` for the first time past the point it used to crash. The mutant
labeled `"branch-delete: -D no longer marks a delete call"` (drops `"-D"` from
`BRANCH_DELETE_FLAGS`) went 1 red. It did not go red on its required case:

```
branch-delete: -D no longer marks a delete call
  required case: 'branch: a commit found nowhere else is the only copy, and the rule denies'
```

A different case went red instead. The harness reported `WRONG CAUSE`.

## What was checked

The affected code is pure Python. It has no platform branch. It makes no real `git`
call in its own path:

- `branch_delete_names` (`hooks/guard.py`) is a set-membership loop over
  `BRANCH_DELETE_FLAGS`. Dropping `"-D"` makes `delete` stay `False` for any `-D` call.
  The function then returns `[]`.
- The dispatcher in `git_calls` (`hooks/guard.py`, around line 726) reads:

  ```
  if subcommand == "branch":
      names = branch_delete_names(args)
      if names:
          return ..., "branch-delete", args
      continue
  ```

  With `names == []`, the `continue` fires. The call is never classified as
  `"branch-delete"` at all. No subject read runs. No real `git` subprocess call
  happens for this call.

Reproduced by hand on Linux. One mutation was applied to a scratch copy of `guard.py`.
`hooks/test_guard.py` then ran against that copy:

```
FAIL  allow (want deny  )  branch: a commit found nowhere else is the only copy, and the rule denies
FAIL  allow (want deny  )  branch: one safe name and one only-copy name in the same call still denies
FAIL  allow (want deny  )  branch: local main's fallback still denies an only-copy branch
FAIL  allow (want deny  )  branch: local master's fallback still denies an only-copy branch
FAIL  wrong (want logged)  log: a branch delete with no resolvable base is allowed and noted
```

Five red lines came back. The first one is the required case. This matches
`mutate_guard.py` reporting `KILLED` for this mutant on Linux and macOS.

## What remains unexplained

The real Windows run reported only 1 red line. That line was not the one above. The
code this mutation breaks never reaches a real `git` call. It has no platform-specific
branch. Nothing in the source explains why Windows would produce a different, smaller
set of red lines. Three candidates were checked and ruled out by reading the code:

- **Fixture build differences** (line endings, `core.autocrlf`, path length). The
  mutated dispatch path exits before any of the five affected cases run their real
  `git` subject calls. A Windows-only quirk in those calls could not produce this
  mismatch.
- **Parallel-mutant collisions.** Each `test_guard.py` subprocess builds its own
  `ROOT = tempfile.mkdtemp(...)` at import time. `mutate_guard.py` gives every mutant
  its own copy of `guard.py` and its own `CLAUDE_CONFIG_DIR`. `mkdtemp` gives a unique
  path on any platform. Nothing here is shared between mutants running at once.
- **Test ordering inside one suite run.** `test_guard.py`'s `main()` runs cases in a
  plain sequential loop, with no threads. Case order inside one process cannot explain
  a leak between cases.

No Windows machine was available to reproduce this directly. Guessing a fix here would
risk hiding the real defect. A patch could change the reported verdict, and still miss
whatever Windows-only behavior actually caused it.

## What this decision does

Nothing changes in `hooks/guard.py` or `hooks/mutate_guard.py` for this mutant. It
still runs, unmarked, on every platform, including the advisory `gates-windows` job.
Weakening or skipping it would hide a real defect if one exists. This entry exists so
the next reader of this mutant's Windows run can see the Linux-side investigation
already ran. It came up empty. It should not be repeated from scratch.

## Next step, if this is worth a real Windows session

Run `hooks/mutate_guard.py` on a real Windows box. Set `MUTATE_JOBS=1`. Filter to just
this one mutation. Capture the full stdout of that one subprocess run, not only the
harness's own one-line summary. That shows which case went red, and why. One such run
would settle the real cause. It is a Windows-only `git` behavior difference, a harness
artifact, or a fixture bug the Linux reproduction did not surface.
