# A cited check must prove it works, not that it exists

## Ruling

CLAUDE.md: "Trust a guard only once it goes red on the defect it guards." The rule audit (`lint/rule_audit.py`) therefore does not cite a gate by a `needle`, a substring that a docstring or label also satisfies.

- A `gate` row cites a `test` id (`path::name`, `path::Class.name`) or a `setting` value. A `needle` is refused.
- The audit resolves the id from the AST. It accepts a method of a `unittest.TestCase` subclass with no skip marker. It accepts a case function that module-level code names, directly or through a function it names. It accepts a case registered by a literal first argument to `add(`, `sh(` or `check(` in code that runs.
- It refuses a name in a docstring or comment, a duplicate `def`, a skip marker, and a `test*` method outside a TestCase class. It also refuses a name reached only under `if False:` or inside an uncalled function.
- `.mjs` ids match a line-anchored `test("name",` registration, after block comments and template literals are removed. That is a named bandaid: no JavaScript parser ships here.
- The test file must also touch the row's `ref`: be it, import it, or pass its file name to a call.
- A `setting` row reads the parsed JSON value, `equals` or `contains`.
- Where no test exercises the behaviour, the row reads `unmechanized` with the reason.
- Every "silent" case pairs with a known-bad input in the same case, so a stub that is silent for all input fails it.
- Each changed check has a known-bad input. Fixture tests carry it for the audit (`lint/test_rule_audit.py`), the verdict (`hooks/test_mutate_shared.py`) and the manifest check (`lint/test_check_landed_dirs.py`). The stub hooks are mutants in `hooks/mutate_guard.py`, through the targets `decision` and `ruling`. No second harness.

Why: a needle passes on text that does nothing, and a stub hook that exits 0 silent for every input passed the "silent" cases.

Limit: the audit proves a cited test exists and that static reading finds no reason it would not run. It does not run the test. A function reached only through a dynamic lookup reads as dead and is refused. The proof of red stays with the mutants and fixture tests, under `mutant-cause-of-death` (a mutant's own cause of death must be the one its label names).

Kind: process
Home: lint/rule_audit.py
