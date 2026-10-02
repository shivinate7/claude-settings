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
  A `needle` is refused. The audit resolves the id from the AST, and refuses every form it
  cannot prove runs. It accepts three forms. One is a method of a `unittest.TestCase`
  subclass with no skip marker. One is a case function that module-level code names, directly
  or through a function that code names. One is a case registered by a literal first argument
  to `add(`, `sh(` or `check(` in code that runs. It refuses six forms. One is a name in a docstring or comment. One is a duplicate `def`.
  One is a skip marker. One is a `test*` method outside a TestCase class. Two are a name reached only under
  `if False:` or inside an uncalled function. `.mjs` ids match a line-anchored
  `test("name",` registration. Block comments and template literals are removed first. That
  is a named bandaid: no JavaScript parser ships here.
- The test file must also touch the row's `ref`: be it, import it, or pass its file name to a
  call. A test of some other file proves nothing about the gate. `verification-report-unknown-reads`
  now cites `hooks/test_guard.py`, where the cited case runs, not the contract script that
  only calls it.
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

The audit proves a cited test exists and that static reading finds no reason it would not run.
It does not run the test, and it does not prove the test goes red on the defect it names. A
function reached only through a dynamic lookup reads as dead and is refused. The proof of red
stays with the mutants and fixture tests above. The mutants follow mutant-cause-of-death, a
mutant's own cause of death must be the one its label names. Each stub mutant names the case
that must fail. The `ruling` target gets a tree that lets the copy import its helper.
