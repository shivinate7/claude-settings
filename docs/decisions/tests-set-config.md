---
id: pending
slug: tests-set-config
---

# A test file must not remove `CLAUDE_CONFIG_DIR` at import and leave it unset

## The ruling

A test file must not pop, delete or `os.environ.clear()` `CLAUDE_CONFIG_DIR` at import and leave it unset. A case that reads the config folder either sets the variable, or uses `isolated_config(run)`, which points it at a fresh folder. An import-time removal is cleared only by a set at import (at module level, or in a function the module calls at import) or by a set in `setUpModule()`. A set in one case does not clear it.

Mistake: `merge/test_merge.py:65` pops `CLAUDE_CONFIG_DIR` at import, in a loop over five names, and never sets it. A builder run of `python3 lint/check_tests_set_config.py` on 2026-11-24 found it: exit 1, one finding.

Harm: a test passes or fails by what the owner's live config holds. A case that writes config may write to the owner's real `~/.claude`.

Helper: `lint/_test_temp.py` `isolated_config(run)`, under the run folder standard (decision `test-temp-standard`). `lint/_test_temp.py` `isolated_config` sets `CLAUDE_CONFIG_DIR` to a fresh folder under the run folder, and yields that folder. On exit, also when the block raises, `lint/_test_temp.py` `isolated_config` restores the old value, or removes the variable when none was set. `lint/_test_temp.py` `isolated_config` sets neither `HOME` nor `USERPROFILE`. It is opt-in. `lint/test_test_temp.py` `IsolatedConfig` is the only caller so far.

Check: `lint/check_tests_set_config.py` parses each `test_*.py` under the repo, skipping dot folders, `node_modules` and `__pycache__`, and reads its import-time statements in source order. It flags a file that does not parse, and a file with a removal of `CLAUDE_CONFIG_DIR` at import that no import-time set follows.

- Removal: `os.environ.pop(...)`, `del os.environ[...]`, or `os.environ.clear()` with no arguments, as a whole statement. The receiver is any `.environ` attribute (in practice `os.environ`), a bare `environ`, or a name bound to one. The name is the string, a name bound to it (annotated or not), a name that a module-level `from <module> import <name>` brings in when that module, beside the file or in `lint/`, binds it to the string at top level, or a loop variable over a literal or module-level tuple that holds it.
- Set: at import, any of these names the variable. An `os.environ` subscript or annotated assignment. `os.environ |= {...}`. `update` or `setdefault` on `os.environ`, through a dict display, a `dict(...)` call, a `**{...}` argument, a keyword, or a name bound at top level to one of these. `os.environ.setdefault(...)` with the name as first argument. An `os.putenv`. `patch.dict(os.environ, ...).start()`. `enter_context(isolated_config(...))`. A call to a module function that does one of these, whatever the order of the defs, so a helper that calls a later-defined helper counts. Import time is the module body and the blocks in it (`if`, `for`, `while`, `try`, `with`, class). A set does not count under a constant-false `if` such as `if False:`, under `if __name__ == "__main__":`, or in a `with patch.dict` block.
- Flagged: an import-time removal with no import-time set after it.
- Clean: no import-time removal, or none after the last import-time set. A set in `setUpModule()` clears every removal in the file.
- Not judged: a removal inside a function, a `patch.dict` block, or `if __name__ == "__main__":`. A set inside one test method, or inside `patch.dict`, does not clear an import-time removal.

Cost: one `ast` parse per `test_*.py` under the repo, per run. A module that a module-level `from <module> import <name>` names beside the file or in `lint/` is parsed at most once per run, however many names it gives. Measured on this repo on 2026-11-25: 8.2 s before the once-per-module read, 2.4 s after. No log, no timer, no long-lived process.

Limits:

- A removal inside a function that the file calls at import. The check does not walk into the function.
- A removal inside an assignment, such as `x = os.environ.pop(...)` at import. Only a bare `pop` or `clear()` statement, or a `del`, counts.
- A name read as an attribute, such as `_consts.CONFIG_VAR`, or a name bound inside a module-level `try` or `if`. Names come only from top-level assignments and `from` imports.
- A module dict that held `CLAUDE_CONFIG_DIR` still counts as holding it after the name is reassigned. `ENV = {"CLAUDE_CONFIG_DIR": x}`, `ENV = {"A": 1}`, a `pop`, then `os.environ.update(ENV)` reads clean.
- `os.unsetenv`: not judged. It also leaves `os.environ` unchanged, so a case that reads `os.environ` still sees the value.
- `os.putenv` counts as a set, but it leaves `os.environ` unchanged. A `pop` then a `putenv` is clean, yet `os.environ.get` still returns None.
- A set made by a function imported from another module. The file stays flagged, though the set runs at import.
- A bare `isolated_config(...)` call that nothing enters does not count. The file stays flagged.
- The check is not in CI or in `merge.readyChecks` yet. `merge/test_merge.py` must set the variable first. The case `test_repo_names_the_incident_file` in `lint/test_tests_set_config.py` expects that file as a finding, so the case fails once the file is fixed. Re-point it then.

Kind: process
Home: lint/check_tests_set_config.py
Done check: `lint/test_tests_set_config.py` (the check's cases) and `lint/test_test_temp.py` (the helper's cases). Run either with `python3 -m unittest discover -s lint -p <file>`, or as `python3 lint/<file>`.
Source: builder run on `merge/test_merge.py`, 2026-11-24. No owner ruling.
