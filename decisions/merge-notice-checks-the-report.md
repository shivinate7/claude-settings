# The merge notice is a check, not a reminder

## The ruling

The merge notice in `hooks/decision_watch.py` fires only for a merge the reply's report does not
name (`verification-cry-wolf-guard-is-spent`).

- `collect_merges` identifies each merge by PR number, read from the `gh pr merge` call's own
  arguments. The command is segment-split first, so a call chained with `;` or `&&` cannot supply a
  number for a merge it did not run. It also reads the number from the MCP merge tool's pull-number
  input. A number it cannot read gives the fixed label `an unnumbered merge`, never the raw command.
- `main()` reads the reply with `ste_gate.last_reply`, and the report block with
  `report_gate.block_text`. `already_named` drops any label the block mentions: `#75`, `PR 75` or
  `PR#75`, without case. The notice lists what is left, spelled `#<N>`.
- One reader finds where a block starts: `report_gate.block_text` and `report_shape_ok` both call
  `find_block_start`. A second scan in `decision_watch.py` could disagree with it
  (`a-gates-allow-list-is-the-constant`).

Cases: `lint/test_gates.py`, `ConfigReportTests`, `test_19` to `test_19e`. Run `python3 lint/test_gates.py`.

Reason: the notice fired when the Done section already named the merge, and it quoted the raw command with its chained `gh pr view`.

Kind: build
Plan: decisions/merge-notice-checks-the-report.md#the-ruling (all)
Home: hooks/decision_watch.py

## Holes, named

A turn that merges and writes no report still fires the notice. That is the safe side.
