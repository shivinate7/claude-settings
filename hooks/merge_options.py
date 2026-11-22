"""The one home of the merge tool's long option names, in the order its parser adds them.

build_parser() in merge/merge.py builds the parser, and a test compares its long options with MERGE_OPTIONS. The guard
(hooks/guard_stream.py) reads it to tell which option a prefix names, as `--lane` for
`--lane-lint`, without importing the merge tool. The tool itself accepts no prefix. Standard library only, no side effect.
"""

MERGE_OPTIONS = (
    "--help", "--repo-dir", "--confirm", "--express", "--lane-lint", "--base", "--lint-unknown-ok", "--with",
    "--touched-tests", "--role", "--step", "--ready", "--fast-checks", "--unlock", "--undo-check-unknown-ok",
    "--base-red-ok", "--session", "--config", "--idle-lanes", "--live", "--reviewed", "--json", "--ledger", "--out",
    "--verdicts", "--subsumed", "--review-tally", "--since", "--split", "--audit-prs", "--root", "--release-check",
    "--lint", "--review-record", "--head", "--kind", "--guard", "--round", "--fix-check", "--grant", "--accepted",
    "--net-value", "--touches", "--run", "--case", "--file",
)
