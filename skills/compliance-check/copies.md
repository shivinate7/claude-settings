# compliance-check: copies

Rule building-one-home-per-capability: a shared thing has one home, and a child extends it.
Shared skills are pinned, never vendored. This probe lists the copies a child holds of
claude-settings files and skills. It reads only, and it fixes nothing.

Run it from the child's root. `$P` is the parent clone.

```
python3 $P/lint/find_copies.py . --parent $P
```

| Exit | Score for the Building group |
| --- | --- |
| 0 | in shape: no copies |
| 1 | partial: each line is a copy |
| 2 | unknown: the child or the parent cannot be read |

Each `skill` line is a vendored skill, with `same` or `drifted` and the count of files that
differ. Each `file` line is a child file that is byte-equal or near-equal to a parent file, with
its score. A copy whose commit message states a reason, such as an owner ruling, is still a
copy: list it, and name the reason.

For each copy, the plan lane is one of these:
- A vendored skill: remove the copy and load the parent's skill, pinned.
- A copied file: call or extend the parent's home. If the child cannot reach the parent at run
  time, such as in CI, the lane is a question for the owner, with options and a recommendation.
