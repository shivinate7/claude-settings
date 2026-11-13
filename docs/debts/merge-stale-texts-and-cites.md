# Merge tool texts and cites name the batch route and retired decisions

**What.** `merge/merge.py` still cites and prints removed things.
- Cites to a batch-CI decision: `BATCH_CITE` (line 221) and `READ_CITE` (line 229) name `no-merge-during-batch-ci`. `RED_CITE` (line 216) names "no batch merges onto a red base". `DROP_CITE` (line 220) names a batch that drops a lane.
- Stale text: the help (line 22) and the docstring at line 3706 say "the batch runner's join". `LANE_LINT_REMEDY` (line 2313) and line 2663 say "join it to a batch". The draft step message (line 3021) says "a run resumes at the wait". The `--release-check` argument help (line 4031) names `--blame`.

**Where.** `merge/merge.py`, the cite constants at lines 216 to 229 and the texts named above.

**Decision.** `no-merge-during-batch-ci` (the batch-CI decision these cites name; its retirement is pending).

**Retire.** Cite the per-lane rule `git-red-main-reverts` and the per-lane decision instead. Reword each text to the per-lane flow. Check: a case in `merge/test_merge.py` that finds none of the named phrases in `merge/merge.py`. Red on the current text, green after the fix.
