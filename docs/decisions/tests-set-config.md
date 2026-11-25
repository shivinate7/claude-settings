---
id: pending
slug: tests-set-config
---

# A test file must not pop the config folder at import and leave it unset

## The ruling

A test file must not pop or delete `CLAUDE_CONFIG_DIR` at import and leave it unset. A case that reads the config folder either sets the variable, or uses `isolated_config(run)`, which points it at a fresh folder.

Mistake: `merge/test_merge.py:65` pops `CLAUDE_CONFIG_DIR` at import, in a loop over five names, and never sets it. A builder run of `python3 lint/check_tests_set_config.py` on 2026-11-24 found it: exit 1, one finding.

Harm: a test passes or fails by what the owner's live config holds. A case that writes config may write to the owner's real `~/.claude`.

Helper: `isolated_config(run)` in `lint/_test_temp.py`, under the run folder standard (decision `test-temp-standard`). It sets `CLAUDE_CONFIG_DIR` to a fresh folder under the run folder and yields that folder. On exit, also when the block raises, it restores the old value, or removes the variable when none was set. It sets neither `HOME` nor `USERPROFILE`. It is opt-in: a case calls it. No test file outside `lint/test_test_temp.py` calls it yet.

Check: `lint/check_tests_set_config.py` parses each `test_*.py` under the repo. It flags a file that pops or deletes `CLAUDE_CONFIG_DIR` at import and never sets it. It also flags a file that does not parse.

- Flagged: an import-time pop or del, with no later module-level set and no set in `setUpModule()`.
- Clean: an import-time pop that a later module-level set or a set in `setUpModule()` clears. A file that never names the variable in a pop or del. A pop inside a function or a `patch.dict` block, which the check does not judge.
- A set inside one test method, or inside `patch.dict`, does not clear an import-time pop.

Cost: one `ast` parse per `test_*.py` under the repo, per run. No log, no timer, no long-lived process.

Limits:

- Only import-time pops and dels are judged. A pop inside a function or a `patch.dict` block is not.
- A name counts only as a string literal, or as a loop variable over a literal. A pop through a constant is not judged. `os.unsetenv` is not judged.
- The check is not in CI or in `merge.readyChecks` yet. `merge/test_merge.py` must set the variable first. Its case `test_repo_names_the_incident_file` expects that file as a finding, so the case fails once the file is fixed. Re-point it then.

Kind: build
Home: lint/check_tests_set_config.py
Done check: `lint/test_tests_set_config.py` (the check's cases) and `lint/test_test_temp.py` (the helper's cases).
Source: builder run on `merge/test_merge.py`, 2026-11-24. No owner ruling.
