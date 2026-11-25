---
id: pending
slug: tests-set-config
---

# A test file must not remove the config folder at import and leave it unset

## The ruling

A test file must not pop, delete or `os.environ.clear()` `CLAUDE_CONFIG_DIR` at import and leave it unset. A case that reads the config folder either sets the variable, or uses `isolated_config(run)`, which points it at a fresh folder.

Mistake: `merge/test_merge.py:65` pops `CLAUDE_CONFIG_DIR` at import, in a loop over five names, and never sets it. A builder run of `python3 lint/check_tests_set_config.py` on 2026-11-24 found it: exit 1, one finding.

Harm: a test passes or fails by what the owner's live config holds. A case that writes config may write to the owner's real `~/.claude`.

Helper: `lint/_test_temp.py` `isolated_config(run)`, under the run folder standard (decision `test-temp-standard`). `lint/_test_temp.py` `isolated_config` sets `CLAUDE_CONFIG_DIR` to a fresh folder under the run folder, and yields that folder. On exit, also when the block raises, `lint/_test_temp.py` `isolated_config` restores the old value, or removes the variable when none was set. `lint/_test_temp.py` `isolated_config` sets neither `HOME` nor `USERPROFILE`. It is opt-in. `lint/test_test_temp.py` `IsolatedConfig` is the only caller so far.

Check: `lint/check_tests_set_config.py` parses each `test_*.py` under the repo and reads its import-time statements in source order. It flags a file that does not parse, and a file with a removal of `CLAUDE_CONFIG_DIR` at import that no import-time set follows.

- Removal: `os.environ.pop(...)`, `del os.environ[...]`, or `os.environ.clear()` with no arguments. The receiver is `os.environ`, a bare `environ`, or a name bound to either. The name is the string, a name bound to it, a name that a module-level `from <module> import <name>` brings in when that module binds it to the string at top level, or a loop variable over a literal or module-level tuple that holds it.
- Set: an `os.environ` assignment, annotated assignment, `update` or `setdefault` that names the variable; an `os.putenv` that names it; or a call at import to a module function that does one of these. It counts when it runs at import: at module level, or in an `if`, `for`, `while`, `try` or `with` block. It does not count under a constant-false `if` such as `if False:`, or in a `with patch.dict` block.
- Flagged: an import-time removal with no import-time set after it.
- Clean: no import-time removal, or none after the last import-time set. A set in `setUpModule()` clears every removal in the file.
- Not judged: a removal inside a function or a `patch.dict` block. A set inside one test method, or inside `patch.dict`, does not clear an import-time removal.

Cost: one `ast` parse per `test_*.py` under the repo, per run, and one more for each name a module-level `from <module> import <name>` takes from a module beside the file or in `lint/`. No log, no timer, no long-lived process.

Limits:

- A removal inside a function that the file calls at import. The check does not walk into the function.
- A removal inside an assignment, such as `x = os.environ.pop(...)` at import. Only a bare `pop` or `clear()` statement, or a `del`, counts.
- A name read as an attribute, such as `_consts.CONFIG_VAR`, or a name bound inside a module-level `try` or `if`. Names come only from top-level assignments and `from` imports.
- `os.unsetenv`: not judged. It also leaves `os.environ` unchanged, so a case that reads `os.environ` still sees the value.
- `os.putenv` counts as a set, but it also leaves `os.environ` unchanged. A `pop` then a `putenv` is clean, and `os.environ.get` returns None.
- A set made by a function imported from another module. The file is flagged, though the set runs at import.
- A helper that calls a helper defined after it. The helper is not seen as a set, so its import-time call is flagged.
- The check is not in CI or in `merge.readyChecks` yet. `merge/test_merge.py` must set the variable first. Its case `test_repo_names_the_incident_file` expects that file as a finding, so the case fails once the file is fixed. Re-point it then.

Kind: process
Home: lint/check_tests_set_config.py
Done check: `lint/test_tests_set_config.py` (the check's cases) and `lint/test_test_temp.py` (the helper's cases). Run either with `python3 -m unittest discover -s lint -p <file>`, or as `python3 lint/<file>`.
Source: builder run on `merge/test_merge.py`, 2026-11-24. No owner ruling.
