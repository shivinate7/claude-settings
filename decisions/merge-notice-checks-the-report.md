# The merge notice is a check, not a reminder

CLAUDE.md: "A guard that goes red when nothing is wrong is spent, because
the reader learns to scroll past it." And: trust a guard only once it goes
red on the defect it guards.

## What was measured

The owner measured this on 2026-09-20. A turn merged PR 75. Its own reply
named the merge under Done. `hooks/config_report.py`'s Stop hook still
printed:

```
Merges into main this turn: gh pr merge 75 --squash --delete-branch ; gh pr
view 75 --json state,mergedAt --jq .mergedAt. Name them in the report.
```

His words: "I already see when things merge under the done section, this is
kinda unnecessary." Two faults, one turn. The notice never read the reply.
It fired even when the report already said the same thing. It also quoted
the RAW command line, including the `gh pr view` chained onto it with `;`.

## The fix

`collect_merges` in `hooks/config_report.py` now identifies each merge by PR
NUMBER. It reads the number from the `gh pr merge` call's own arguments. The
command is segment-split first, so a call chained with `;` or `&&` cannot
supply a number for a merge it did not run. It also reads the number from
the MCP merge tool's own pull-number input. A merge whose number cannot be
read falls back to the fixed label `an unnumbered merge`, never to the raw
command text.

`main()` then reads the reply's own text with `ste_gate.last_reply`. It asks
`report_gate.block_text` for the reply's report block. That is the same
blockquote extractor `lint/report_gate.py`'s own shape check runs on.
`already_named` drops any label the block already mentions: `#75`, or `PR
75`, or `PR#75`, matched without case. The notice is built from what is
left. A merge already named under Done no longer gets a second mention. A
merge the reply never named still fires, spelled `#<N>`.

## Reuse, not a second parser

CLAUDE.md: "a gate's allow list must point at the constant the code emits,
never a copy of it." `report_gate.py` already draws the line for where a
reply's report block starts. It draws that line for its own shape check.
Reading the block text a second way, with a hand-rolled scan in
`config_report.py`, would be exactly the copy this rule warns against. The
two readers could then disagree about where the block starts.
`config_report.py` would judge "named" or "not named" against a boundary
`report_gate.py` does not use.

Importing `report_gate` directly needed no circular import.
`lint/report_gate.py` already imports `hooks/guard.py`, for its own git-call
resolution. `hooks/config_report.py` already imports `hooks/guard.py` too.
The import graph gains one edge, `hooks/config_report.py` to
`lint/report_gate.py`. It gains no cycle. `report_shape_ok` was left
untouched. A new function, `block_text`, was factored out beside it, built
on the same `find_block_start` helper `report_shape_ok` itself now calls.
The two functions cannot drift on where a block starts.

## Fixtures

`lint/test_gates.py`, `ConfigReportTests`:

- `test_19_merge_into_main_after_last_human_names_it_by_pr_number`: the PR
  number appears, not the raw command. `--squash` does not appear.
- `test_19a_merge_named_in_the_report_stays_silent`: report already says
  `#75` under Done. No output.
- `test_19b_merge_omitted_from_the_report_still_fires`: report omits it.
  `#75` fires.
- `test_19c_chained_gh_pr_view_does_not_ride_along`: `gh pr merge 75
  --squash` chained with `gh pr view 75 --json state,mergedAt`. Only `#75`
  is named. `gh pr view` and `--json` never appear in the notice.
- `test_19d_several_merges_in_one_turn_are_all_named`: two merges land. One
  is already named in the report, one is not. Only the unnamed one fires.
- `test_19e_unreadable_pr_number_falls_back`: `gh pr merge --auto --squash`
  carries no number. It falls back to `an unnumbered merge`.

`test_19a`, `test_19b`, and `test_19c` were run against the pre-fix
`hooks/config_report.py` first. All three failed red. The old code always
fired. It always printed the raw command line. They passed once the fix
landed.

## Holes, named

This notice now depends on the reply's own shape. A turn that merges and
writes no report at all gets an empty block from `report_gate.block_text`.
`already_named` then keeps every label unfiled, so the notice still fires.
That is the safe side of the hole.

The unsafe side is the opposite case. A reply's blockquote could hold the
digits of a merged PR's number for an unrelated reason. A commit SHA
fragment, a port number, another PR's number written nearby, any of these
can supply the digits. `already_named` narrows this by requiring the number
to follow `#` or `PR`/`pr`, never a bare digit run alone. A coincidental
string like `PR 75` elsewhere in the block would still suppress a real,
unnamed merge of PR 75. Nothing here checks that the mention refers to the
merge this hook is naming, and not some other PR sharing its number.

## The mechanism

This entry adds no new CLAUDE.md rule anchor. It implements the existing
`verification-cry-wolf-guard-is-spent` rule, for one guard: the merge notice
in `hooks/config_report.py`. The fixtures above are its mechanism. Run them
with `python3 lint/test_gates.py`.
