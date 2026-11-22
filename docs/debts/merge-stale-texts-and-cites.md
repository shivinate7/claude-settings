# Merge tool texts and cites name the batch route and retired decisions

**What.** `merge/merge.py` still cites and prints removed things.
- Cite to a batch-CI decision: `READ_CITE` names `no-merge-during-batch-ci`.
- Stale text: `LANE_LINT_REMEDY` and a comment tail in the merge tool say "join it to a batch". The draft step message says "a run resumes at the wait".

**Where.** `merge/merge.py`, the cite constant `READ_CITE` and the texts named above.

**Decision.** `no-merge-during-batch-ci` (the batch-CI decision these cites name; its retirement is pending).

**Retire.** Cite the per-lane rule `git-red-main-reverts` and the per-lane decision instead. Reword each text to the per-lane flow. Check: a case in `merge/test_merge.py` that finds none of the named phrases in `merge/merge.py`. Red on the current text, green after the fix.
