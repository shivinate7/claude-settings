# The branch-delete wrong-cause on Windows was a filename collision

`decisions/branch-delete-wrong-cause-on-windows-unexplained.md` named a real defect and
said its cause stayed unexplained. The cause is now found. This entry replaces that one.

## The mechanism

`hooks/mutate_guard.py`'s `run_mutant` names each mutant's copy file with
`safe_name(label)`, and names its config directory `cfg_<safe_name>`. The old `safe_name`
mapped every non-alphanumeric character to an underscore and kept letter case.

Two real labels differ only by the case of one letter:

```
branch-delete: -D no longer marks a delete call
branch-delete: -d no longer marks a delete call
```

Both mapped to the same file name, `guard_branch_delete___d_no_longer_marks_a_delete_call.py`,
and the same config directory. Windows treats file names as case-insensitive. Linux and
macOS do not. The harness runs many mutants at once, so on Windows the two writers raced.
Whichever wrote last won, and both suites then ran against that one mutated copy.

## What was measured

Three facts, measured directly, not guessed.

1. This is the only collision in the list. Of 106 labels, 106 are unique by exact text.
   Only 105 are unique once letter case is folded away.
2. The winner flips between machines, which is what a race looks like. Real Windows CI
   run 35678689541 gave `-D` a `WRONG CAUSE` verdict with 1 red line, and gave `-d` a
   `KILLED` verdict. A second Windows machine gave the opposite split, 5 red lines each,
   with the `-d` run missing its required case.
3. Applied alone, on its own copy, the `-D` mutation produces its required red line among
   five. The mutation itself is correct. Only its shared file name was wrong.

## The three ruled-out candidates were each correct

The earlier entry checked fixture build differences, parallel-mutant collisions, and test
ordering inside one suite run. It ruled out all three by reading the code, and it was
right to rule out all three. None of them caused this. The real cause was a file name that
two mutants shared on one platform. It was never the platform itself, and never a defect
in the mutated code.

## The fix

`safe_name` now appends a short digest of the exact label to its output. The digest
covers the label's exact bytes, case included, so it separates any two labels that
differ only by case without hand-coding a case rule. It does not depend on the label's
position in `MUTATIONS`, so reordering the list never reassigns a mutant's file name.

`hooks/mutate_guard.py`'s `main` now also refuses to start when two mutants would still
share one path on a case-insensitive filesystem, checked before any suite runs. Proven
by a temporary duplicate label. The check printed `ERROR two mutations share one path on
a case-insensitive filesystem` and returned 1. No test process started.

## What this closes

Both `-D` and `-d` branch-delete mutants now run against their own copy. Driven together
at the harness's default concurrency, both report `KILLED`.
