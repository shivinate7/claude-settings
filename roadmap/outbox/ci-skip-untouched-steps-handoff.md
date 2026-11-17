# Handoff: lane ci-skip-untouched-steps

Goal (owner, 11:20 CST Nov 13, via runner 10, R67 part 4 express): make CI skip jobs and the `checks` job's steps when a change does not touch what they read. No fixed time targets (owner R37).

## Landed

- Slice 1: #3158 merged Nov 14 19:05Z (four PR-only lint steps scoped by `lint_*` flags in `.github/scripts/ci-scope.sh`).
- Slice 2: #3180 closed as replaced by #3408 (merged Nov 14 22:51Z, 75 `checks` steps scoped by `code`).
- Slice 3: #3584 merged Nov 17 17:14 CST (commit fae9721503a7): eight `doc_*` flags in the one scope reader, a doc-group scope condition on 40 steps, `$DOCS` expansion in `merge/merge.py` express. #3385 (first slice 3 try, stacked on the old #3180 tree) closed as replaced. Review record on #3584: rounds FAIL FAIL PASS, net value zero.

## Not measured

The after-number. Gold is my own before/after on the same kind of batch. Before: batch 133, run 43466545532 (all .md): wall 41.4 min, 43.5 job-minutes, `checks` 40.7 min. It needs a docs-only batch on the merged slices.

## Open findings, not landed as note files (for triage)

- The step-scope test (`lint/test_checks_step_scope.py`, item 7) reads each entry file's own text only. It misses `x + ".md"`, `"%s.md" % x` and variable joins in helpers (`lint/report_guard.py`, `lint/check_landed_dirs.py`), so a later read in 9 of the 19 group-limited steps would pass unseen. Follow-up lane: scan every reached file's read calls for tracked `.md` names.
- The missing-`LINTS=` refusal in `merge/merge.py` has no test.
- Decision `records-index-at-merge` says "steps that read a .md file still run" on a records-only push. After per-group scoping that is stale for 15 of 40 steps (none opens `docs/records.md`; no hole). Two comments repeat it: `.github/workflows/checks.yml` near the records-only comment, and `lint/test_ci_scope.py` near line 901. Main's job-level records-only skip now skips whole jobs. Owner flag.
- `merge/test_holds_head.py` and `merge/test_lost_work.py` open root `CLAUDE.md`, the output style and `docs/decisions` through imports in `merge/test_merge.py`, in a job outside the step-scope test (already `code` only on main). Effect on verdicts unmeasured.
- The merge tool's `--fix-check` refuses a chain of clean main merges followed by one plain commit. The record names the fix check in prose.
- Fixture-move follow-up lanes (suites that read a real doc move the read into a fixture so the step can drop its doc flag): Reply judge, Precompact, SendMessage state, Question form, Agent brief, Blind brief, report_guard suites, rule audit, stale prose, hook catalog, glossary, STE, Scratchpad owner and Guard wrappers.
- Refusals this lane met: the auto-mode classifier refused `bash merge/install_from_main.sh` ([Undermining Oversight]) and `merge 3584 --confirm` ([Destructive or Unwanted Actions]); runner 10 merged #3584. Owner ruling `own-lanes-merge-claude-settings-prs` says lanes merge their own; the allow entry for that act is missing.
