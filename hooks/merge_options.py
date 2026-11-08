"""The one home of the merge tool's long option names, in the order its parser adds them.

merge/merge.py builds its parser and checks it against MERGE_OPTIONS on every run. The guard
(hooks/guard_stream.py) reads it to tell which option an argparse prefix names, as `--lane` for
`--lane-lint`, without importing the merge tool. Standard library only, no side effect.
"""

MERGE_OPTIONS = (
    "--help", "--confirm", "--lane-lint", "--base", "--lint-unknown-ok", "--role", "--unlock",
    "--undo-check-unknown-ok", "--base-red-ok", "--session", "--config", "--idle-lanes", "--live",
    "--reviewed", "--review-record", "--head", "--kind", "--guard", "--round", "--fix-check",
    "--net-value",
)
