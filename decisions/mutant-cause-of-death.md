# A mutant proves nothing until its own cause is checked

CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." This
entry is that sentence applied to the guard's own test harness. `hooks/mutate_guard.py`
judged a mutant "killed" on a nonzero exit plus any red line in the suite's output. Two
separate mutants used that same generic check to hide two different real defects.

## What was measured

`hooks/mutate_guard.py`'s verdict loop read:

```
if code == 0 or not red:
    survivors += 1
else:
    print("KILLED ...")
```

Any red line counted, whichever case printed it. A mutant that broke the waiter rule
could die on an unrelated shared-tree case. It would still print `KILLED`.

Fixing that meant giving each of the 69 `MUTATIONS` entries a required case name. Every
one then had to run for real, to find out what actually kills it. That run surfaced a
second defect. No test had caught it, because the verdict loop never asked.

All 7 `watch`-target mutants (the ones that mutate `config_watch.py`, run by
`hooks/test_config_watch.py`) printed the SAME nine `FAIL` lines. The lines matched word
for word, whichever line had been mutated:

```
FAIL  [bypass]  pre=allow  cp from another file  (cap STILL LIFTED: the watch missed it)
FAIL  [bypass]  pre=allow  mv from another file  (cap STILL LIFTED: the watch missed it)
... (seven more, identical across all seven mutants)
```

The cause was not the mutation. A `watch` mutant is written to a temp directory outside
`hooks/`, then run as its own subprocess. `config_watch.py` does a plain `import guard`
there. That is deliberate. `test_config_watch.py`'s `Project.env()` strips
`GUARD_UNDER_TEST` before it spawns the copy. So a watch mutation is never judged
against a guard that moved with it. Without the real `guard.py` beside the copy, that
import raised `ModuleNotFoundError` on every mutant. It crashed before any watch logic
ran. The crash read as "the watch missed every case," regardless of what had been
mutated.

MEASURED: copying the unmutated `config_watch.py` alone to an empty temp directory, then
running it, reproduces the identical crash. The bug had nothing to do with any one
mutation.

## Why "any red line" hid this for an unknown length of time

The mutants were doing nothing. Not "doing the wrong thing." Doing nothing at all,
crashing before the first watched path was even read. The harness still printed
`KILLED` for all seven. A crash gives a nonzero exit. The crash traceback, plus the
always-allow fallback already built into `Project.pre()` and `Project.post()`, gave the
red lines too. A green mutation run on `main`, for as long as these seven mutants
existed, proved the harness could exit 1. It proved nothing about `config_watch.py`.

This is the same shape as the two false alarms `decisions/predicate-is-the-act.md`
already recorded. A check matched on a SHAPE of failure: a nonzero exit, a red line, a
matched string. It never resolved the ACT the check exists to catch, which is whether
THIS suite fails BECAUSE of THIS mutation. The predicate was the shape, not the act.
This time the predicate lived in the harness itself, not in a gate the harness runs.

## The fix

Two changes, both in `hooks/mutate_guard.py`:

- Every mutant now carries a required case name. The verdict loop checks that name
  against its own red lines, not just their presence. A mutant whose FAIL lines miss the
  name it claims to break reports `WRONG CAUSE`. That verdict stays distinct from
  `SURVIVED`, and it fails the run.
- The mutant work directory now carries a copy of the real, unmutated `guard.py`
  alongside every `watch` mutant. `import guard` then resolves to it, instead of
  crashing.

The required-name field caught nothing by itself here. It cannot see a crash it was
never told to expect. A manual read of the identical nine-line output found this, run
before the new field was trusted. The field's own worth was proven the same way.
Pointed at a case a mutation cannot break, it reported `WRONG CAUSE`, not `KILLED`,
before it judged the real 69.

## The rule this sets

A harness that judges its own tests by exit code, or by "some output changed," makes
the same error the guards it tests are built to avoid. Verify a test harness the way
`predicate-is-the-act.md` asks a gate to be verified. Name the specific case the change
must produce. Confirm that case, never a shape near it. An exit code is a shape. A
named, checked case is the act.

## Holes, named

- The fix colocates `guard.py` for `watch` mutants only. It does not audit whether some
  other mutant, of either target, could crash for a different, still-unseen reason. Such
  a crash could still read as a false `KILLED` the same way. The required-name field
  narrows this risk, because a crash's output rarely happens to contain the exact case
  name a mutation claims to break. A future crash of this shape is more likely to show
  as `WRONG CAUSE` now. It is not proof against every crash shape.
- One mutation, "watch: an absent file reads the same as an empty one," needed a new
  fixture case in `hooks/test_config_watch.py` before it had anything to die on. That
  case now exists: `a file goes from empty to absent before a lift, so the revert
  removes it, not empties it`. Building it is a second instance of the same lesson. The
  first fixture tried for it did not distinguish the mutation either. `load_baseline`
  recomputes a fresh digest by hand for a stored `None` content, rather than trusting
  the one that was saved. That makes `digest(None)` unreachable from that angle. The
  case that actually kills it starts from a REAL empty file, not an absent one, then
  deletes it. A required name is only as good as the case behind it. A case is only as
  good as its own trace through the code, never a guess from the mutation's label.
