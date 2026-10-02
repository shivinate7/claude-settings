# A cited check must prove it works, not that it exists

CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards." The rule
audit (`lint/rule_audit.py`) cited gates by a `needle`: a substring that must still appear in
the gate file. A needle passes on a docstring or a label. It never runs the check.

## What was measured

Four needles in `lint/rule_mechanisms.json` sat on text that does nothing: a docstring
("drives the guard as Claude Code drives it"), two verdict labels (`SURVIVED`, `WRONG CAUSE`),
and a code-fence literal in `lint/report_gate.py`. Three settings rows checked a name
(`CLAUDE_CODE_SUBAGENT_MODEL`, the spawn-depth variable, `hooks/guard.py`) and not its value.
Setting the model to `opus` left the row green.

Two "silent" cases in `hooks/test_decision_watch.py` and `hooks/test_ruling_home.py` asserted
exit 0 and empty output. A hook stub that exits 0 silent for every input passes both. One
silent ruling-home case also used a home that resolves, so the fail-open path it names read
silent with or without the failure.

## Ruling

- A `gate` row cites a `test` id (`path::name`, `path::Class.name`) or a `setting` value.
  A `needle` is refused. The audit resolves the id from the AST: a `def` that unittest
  collects or a runner references, or a case registered by a literal first argument to
  `add(`, `sh(` or `check(`. A name inside a docstring, a comment, or a duplicate `def`
  does not resolve. `.mjs` ids match a line-anchored `test("name",` registration, a named
  bandaid: no JavaScript parser ships here.
- A `setting` row reads the parsed JSON value, `equals` or `contains`.
- Where no test exercises the behaviour, the row reads `unmechanized` with the reason.
  Three rows moved: `verification-verify-against-repo`, `verification-never-dry-run-blocklist`,
  `reports-drop-unused-label`. `UNMECHANIZED_EXPECTED` rose from 72 to 75.
- Every "silent" case pairs with a known-bad input in the same case, so a stub that is silent
  for all input fails it.
- Each changed check has a known-bad input. Fixture tests carry it for the audit
  (`lint/test_rule_audit.py`), the verdict (`hooks/test_mutate_shared.py`) and the manifest
  check (`lint/test_check_landed_dirs.py`). The stub hooks are mutants in
  `hooks/mutate_guard.py`, through two new targets, `decision` and `ruling`. No second harness.

## What this does not prove

The audit proves a cited test exists and is collected. It does not prove the test goes red on
the defect it names. That proof stays with the mutants and the fixture tests above.
