# An opt-in run checks every tracked cite, not only the range

Owner ask, 2026-11-03 15:58 CST, through the coordinator: promote the child repos' guards up to claude-settings. The promotion plan, lane 1 (prose-path-check-whole-tree), sits on origin/child-guard-promotion until that branch merges.

## The ruling

`lint/stale_cites.py --tree [REV]` reads every tracked Markdown file at REV. REV defaults to HEAD. It reads no range, so it fires on lines that no change touched.

- STALE003: a cite with a `/` and a file extension, whose first folder is tracked. The cite names no tracked file or folder. It is checked from the repo root and from the folder of the Markdown file. When one tracked file has the same name, the message names it.
- STALE004: a `path:N` or `path:N-M` cite where N is below 1, M is below N, or the last number is past the file's last line.
- Same leave-outs as range mode: the records page, each file in `.ste-lint-exclude` or the EXCLUDE input, and a line marked `ste-disable-line` with STALE003 or STALE004.

The ste-lint input `tree-cites` turns the mode on. Its default is "false". A repo that sets nothing sees no change. The ste-lint step runs tree mode in both scopes, and `fail: false` keeps the exit 0.

Departs from: stale-cites-at-merge range-only — adds an opt-in whole-tree mode that fires on untouched lines

This departs from the ruling's "never red on work the PR did not do" only for a repo that opts in.

## Measured

Measured 2026-11-03 on origin/main at 72034d9a: `python3 lint/stale_cites.py --tree origin/main` gives 70 STALE003 and 0 STALE004.

- Most of the 70 name paths in other repos or at runtime. A few are example text.
- claude-settings does not opt in yet.

## Cost

- One python3 start (unmeasured). Git runs rev-parse, ls-tree and one cat-file --batch. It writes no file.
- `CostTests` in `lint/test_stale_cites.py` proves the git reads. `actions/ste-lint/test_action.py` proves the default is "false".

## Not covered

The plan promotes these child rows to this lane for their path and anchor parts. Tree mode does not cover the parts named here. Each child's removal lane keeps them.

- Code names and links: the mailaudit repo's row 13 in the plan.
- Allowlist and doc hygiene: the banchi repo's row 40 in the plan.
- The hook catalog records list: the degen repo's row 8a in the plan.

Kind: build
Plan: docs/decisions/stale-cites-whole-tree.md#the-ruling (all)
Home: lint/stale_cites.py
